"""`python -m decision_governor.adversarial` — the CI action (Step 6).

Runs the toolkit against a target gate and, optionally, a decision log,
then applies a whitelisted --fail-on expression: nonzero exit prints the
breached clause. No eval() anywhere (see _failon.py).

    python -m decision_governor.adversarial \
        --target myapp.gates:summary_gate \
        --db decisions.db \
        --fail-on "cbw > 0.02 or injection_pass < 0.95"
"""
from __future__ import annotations

import argparse
import importlib
import inspect
from collections.abc import Sequence
from typing import Any

from decision_governor.adversarial import calibration, cascade, injection, shift
from decision_governor.adversarial._failon import FailOnError, evaluate
from decision_governor.adversarial.report import AdversarialReport


def _load_target(spec: str) -> Any:
    """Resolve 'module:attribute' to a gate. The attribute may be a gate
    object (has .evaluate), a bare (output, context) -> Verdict callable,
    or a zero-arg factory returning either — distinguished by whether its
    signature binds zero arguments (factory) or two (bare gate)."""
    module_name, _, attr = spec.partition(":")
    if not attr:
        raise SystemExit("--target must be 'module:attribute' (e.g. myapp.gates:gate)")
    obj = getattr(importlib.import_module(module_name), attr)
    if hasattr(obj, "evaluate"):
        return obj
    if callable(obj):
        try:
            sig = inspect.signature(obj)
        except (TypeError, ValueError):
            sig = None
        if sig is not None:
            try:
                sig.bind()                  # zero-arg call -> a factory
            except TypeError:
                try:
                    sig.bind(object(), {})  # (output, context) -> a bare gate
                except TypeError:
                    raise SystemExit(
                        f"--target {spec!r} is callable but accepts neither zero "
                        "arguments (factory) nor (output, context) (gate)"
                    )
                return obj
        built = obj()                       # a factory returning a gate
        if hasattr(built, "evaluate") or callable(built):
            return built
    raise SystemExit(f"--target {spec!r} is neither a gate nor a factory returning one")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="decision_governor.adversarial",
        description="Run the adversarial toolkit against a gate and gate on its metrics.",
    )
    parser.add_argument("--target", help="module:attribute resolving to a gate or factory")
    parser.add_argument("--db", default=None, help="decision log for cascade/calibration")
    parser.add_argument("--corpus", default="v1", help="injection corpus tag")
    parser.add_argument("--seed", type=int, default=1234, help="seed for randomized tools")
    parser.add_argument("--floor", type=float, default=0.9, help="confidence floor for CBW")
    parser.add_argument("--fail-on", default=None, help="whitelisted failure expression")
    args = parser.parse_args(argv)

    reports: list[AdversarialReport] = []
    metrics: dict[str, float] = {}

    if args.target:
        target = _load_target(args.target)
        reports.append(injection.run(target, corpus=args.corpus))
        # A tiny fixture set drawn from the corpus's benign controls keeps
        # shift self-contained when no fixtures are provided externally.
        fixtures = [
            e["payload"] for e in injection.load_corpus(args.corpus)
            if e.get("expected_catch") is None
        ]
        if fixtures:
            reports.append(shift.run(target, fixtures, seed=args.seed))

    if args.db:
        from decision_governor.instrumentation.sinks import SQLiteSink

        records = list(SQLiteSink(args.db).query())
        reports.append(calibration.confident_but_wrong(records, confidence_floor=args.floor))
        target_obj = _load_target(args.target) if args.target else None
        policy = getattr(target_obj, "policy", None)
        if policy is not None and type(policy).__name__ == "CVaRPolicy" and records:
            marginals = cascade.marginals_from_records(records, policy)
            theta, source = cascade.fit_theta(records)
            reports.append(
                cascade.run(policy, marginals, seed=args.seed, theta=theta, theta_source=source)
            )

    for report in reports:
        metrics.update(report.metrics)
        print(report.to_json().decode("utf-8"))

    if args.fail_on:
        try:
            breached, clause = evaluate(args.fail_on, metrics)
        except FailOnError as exc:
            print(f"--fail-on error: {exc}")
            return 2
        if breached:
            print(f"FAIL: breached clause -> {clause}")
            return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
