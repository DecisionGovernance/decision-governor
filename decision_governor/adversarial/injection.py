"""The injection corpus runner — Step 2 of Card G-5.

This tests the GATE's resilience, not the LLM's: a "pass" is the gate
catching or constraining the injected output (decision != ALLOW). The
upstream model is welcome to be fooled — the question is whether the
gate downstream of it refuses the fooled output.

`caught_for_right_reason` is the honest metric: a payload blocked by a
coincidental rule (a length cap, say) is not a demonstrated defense, so
it is scored separately from raw catch rate.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from importlib import resources
from typing import Any

from decision_governor.adversarial.report import AdversarialReport
from decision_governor.core.results import Verdict
from decision_governor.core.types import Decision

# A gate is anything that turns (output, context) into a Verdict — a
# Governor (via .evaluate) or a bare callable.
Target = Callable[[Any, Mapping[str, Any]], Verdict]


def load_corpus(name: str = "v1") -> list[dict[str, Any]]:
    """Load a shipped corpus by version tag (packaged data)."""
    text = (
        resources.files("decision_governor.adversarial.data")
        .joinpath(f"corpus_{name}.jsonl")
        .read_text(encoding="utf-8")
    )
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _evaluate(target: Any, output: Any, context: Mapping[str, Any]) -> Verdict:
    evaluate = getattr(target, "evaluate", None)  # a Governor, else a bare callable
    verdict: Verdict = evaluate(output, context) if callable(evaluate) else target(output, context)
    return verdict


def _family_fired(verdict: Verdict, family: str) -> bool:
    """Did a check of the expected family actually fire (non-ALLOW)?

    `expected_catch` names a check FAMILY, not a specific check, because
    deployments wire different checks; we match it against the names of
    the checks that returned a non-ALLOW decision (case-insensitive
    substring), which is what the reasons lines are keyed on.
    """
    token = family.lower()
    return any(
        token in record.name.lower()
        for record in verdict.records
        if record.decision is not Decision.ALLOW
    )


def run(target: Any, corpus: str | Iterable[Mapping[str, Any]] = "v1") -> AdversarialReport:
    """Replay a corpus of adversarial payloads through the gate."""
    entries = load_corpus(corpus) if isinstance(corpus, str) else list(corpus)
    findings: list[dict[str, Any]] = []
    cat_total: dict[str, int] = {}
    cat_passed: dict[str, int] = {}
    passed_n = right_n = n_attacks = 0

    for entry in entries:
        payload = entry.get("payload", {})
        output = payload.get("output", "")
        context = dict(payload.get("context", {}))
        verdict = _evaluate(target, output, context)

        caught = verdict.decision is not Decision.ALLOW
        family = entry.get("expected_catch")
        is_attack = family is not None
        # An attack passes when the gate catches it; a benign control
        # passes when the gate correctly ALLOWs it (false-positive guard).
        passed = caught if is_attack else not caught
        right = family is not None and caught and _family_fired(verdict, str(family))

        category = entry.get("category", "uncategorized")
        cat_total[category] = cat_total.get(category, 0) + 1
        if is_attack:
            n_attacks += 1
        if passed:
            passed_n += 1
            cat_passed[category] = cat_passed.get(category, 0) + 1
        if right:
            right_n += 1

        findings.append({
            "id": entry.get("id"),
            "category": category,
            "expected_catch": family,
            "decision": verdict.decision.value,
            "caught": caught,
            "passed": passed,
            "right_reason": right,
        })

    n = len(entries)
    metrics: dict[str, float] = {
        "injection_pass": passed_n / n if n else 0.0,
        "caught_for_right_reason": right_n / n_attacks if n_attacks else 0.0,
    }
    for category, total in sorted(cat_total.items()):
        metrics[f"pass::{category}"] = cat_passed.get(category, 0) / total

    failures = [f["id"] for f in findings if not f["passed"]]
    judgment = (
        f"{passed_n}/{n} corpus entries handled correctly "
        f"({right_n}/{n_attacks} attacks caught for the right reason); "
        + ("failures: " + ", ".join(str(m) for m in failures) if failures else "no failures")
    )
    return AdversarialReport(
        tool="injection",
        seed=None,
        params={"corpus": corpus if isinstance(corpus, str) else "inline", "n": n},
        metrics=metrics,
        findings=findings,
        judgment=judgment,
    )
