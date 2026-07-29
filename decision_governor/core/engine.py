"""Card G-1: the Governor, decision composition, and the @gate decorator.

Composition guarantees (proved by property tests, not asserted):
deterministic, order-invariant, and tighten-only. The consequence, read
out loud: a learned component can be the reason an action was
*constrained*, never the reason one was *authorized*.
"""
from __future__ import annotations

import functools
import uuid
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Any, ParamSpec

from decision_governor.core.errors import (
    InvalidPolicy,
    NoChecksRegistered,
    NoLogConfigured,
    UnknownCheck,
)
from decision_governor.core.policy import Policy, ThresholdPolicy
from decision_governor.core.results import CheckRecord, GateResult, Verdict
from decision_governor.core.types import Check, Decision

P = ParamSpec("P")

# Strict severity order: composing verdicts means taking the worst.
_SEVERITY = {Decision.ALLOW: 0, Decision.SCALE: 1, Decision.ABSTAIN: 2}


def _worst(decisions: Sequence[Decision], default: Decision) -> Decision:
    if not decisions:
        return default
    return max(decisions, key=lambda d: _SEVERITY[d])


def _compose(records: Sequence[CheckRecord]) -> Decision:
    det = [r.decision for r in records if r.deterministic]
    nondet = [r.decision for r in records if not r.deterministic]

    # Base comes from deterministic evidence only; with none, ALLOW is
    # unreachable — absence of proof is not permission, ceiling SCALE.
    base = _worst(det, default=Decision.SCALE)

    # Learned checks may only escalate; their absence escalates nothing.
    escalation = _worst(nondet, default=Decision.ALLOW)

    return _worst([base, escalation], default=base)


class Governor:
    """Registry of checks plus the evaluate() that composes their verdicts."""

    def __init__(
        self,
        policy: Policy | None = None,
        log: Any = None,
        deployment: str = "default",
    ) -> None:
        chosen: Policy = policy if policy is not None else ThresholdPolicy()
        if not callable(getattr(chosen, "judge", None)):
            raise InvalidPolicy(chosen, missing="judge")
        self.policy = chosen
        if log is not None:
            # The G-4 seam, now live: Sink object, path string (SQLite),
            # or None. Lazy import keeps core importable on its own.
            from decision_governor.instrumentation.sinks import resolve_sink

            self.log = resolve_sink(log)
        else:
            self.log = None
        self.deployment = deployment
        self._registry: dict[str, Check] = {}

    def register(self, check: Check) -> None:
        self._registry[check.name] = check

    def evaluate(
        self,
        output: Any,
        context: Mapping[str, Any] | None = None,
        scale_path: str | None = None,
        *,
        checks: Sequence[str] | None = None,
    ) -> Verdict:
        # Frozen positional API: (output, context, scale_path). checks is
        # keyword-only so it can never shadow a positional scale_path.
        if not self._registry:
            raise NoChecksRegistered()
        ctx: Mapping[str, Any] = context if context is not None else {}

        if checks is not None:
            for name in checks:
                if name not in self._registry:
                    raise UnknownCheck(name, self._registry)
            names = sorted(set(checks))
        else:
            names = sorted(self._registry)
        # Sorted-name order makes order-invariance trivially true.
        selected = [self._registry[name] for name in names]

        records: list[CheckRecord] = []
        for check in selected:
            result = check.run(output, ctx)
            judged = self.policy.judge(check.name, result, ctx)
            records.append(CheckRecord(check.name, check.deterministic, result, judged))

        per_check_decision = _compose(records)
        decision = per_check_decision
        aggregate_reason: str | None = None
        aggregate_binds = False
        # Aggregate seam: a policy may also judge the gate's combined
        # exposure across all selected checks (CVaRPolicy does; per-check
        # judging alone cannot price aggregate tail risk). Deterministic
        # records must be evaluated independently: a buggy policy must not
        # use a learned record's presence to relax that deterministic result.
        judge_gate = getattr(self.policy, "judge_gate", None)
        if callable(judge_gate):
            deterministic_records = [record for record in records if record.deterministic]
            if deterministic_records:
                deterministic_context = dict(ctx)
                deterministic_gate = judge_gate(deterministic_records, deterministic_context)
                deterministic_risk = deterministic_context.get("risk", {}).get("__gate__")
            else:
                # No deterministic evidence can support ALLOW, even if a
                # policy's empty-set aggregate happens to return it.
                deterministic_gate = Decision.SCALE
                deterministic_risk = None

            all_gate = judge_gate(records, ctx)
            if deterministic_gate is None:
                deterministic_gate = Decision.ALLOW
            if all_gate is None:
                all_gate = Decision.ALLOW
            candidates = [per_check_decision, deterministic_gate, all_gate]
            decision = _worst(candidates, default=per_check_decision)
            aggregate_binds = (
                max(_SEVERITY[deterministic_gate], _SEVERITY[all_gate])
                == _SEVERITY[decision]
            )

            if _SEVERITY[decision] > _SEVERITY[per_check_decision]:
                risk = ctx.get("risk", {}).get("__gate__")
                if _SEVERITY[deterministic_gate] > _SEVERITY[all_gate]:
                    risk = deterministic_risk
                if isinstance(risk, Mapping):
                    if isinstance(ctx, MutableMapping):
                        ctx.setdefault("risk", {})["__gate__"] = dict(risk)
                        ctx["risk"]["__gate__"]["decided_by"] = "aggregate"
                    tail = risk.get("gate_cvar")
                    abstention = risk.get("cost_abstain")
                    checks_count = risk.get("checks")
                    assumption = risk.get("assumption")
                    if all(value is not None for value in (tail, abstention, checks_count, assumption)):
                        aggregate_reason = (
                            f"gate tail cost {tail:.1f} vs abstention {abstention:.1f} "
                            f"({checks_count} checks, {assumption})"
                        )
        # decided_by tri-state (Sunday Review 1 clarification): which
        # mechanism was DECISIVE, most structural first when several bind
        # at the final severity — ceiling > aggregate > per_check, where
        # "ceiling" means the engine's no-deterministic-evidence SCALE cap
        # exclusively (the policy's CVaR bar remains the per-check
        # allow_barred_by_ceiling fact in the risk block). ALLOW verdicts
        # are always per_check: nothing constrained, so nothing "bound".
        has_deterministic = any(record.deterministic for record in records)
        if _SEVERITY[decision] == 0:
            decided_by = "per_check"
        elif not has_deterministic and decision is Decision.SCALE:
            decided_by = "ceiling"
        elif aggregate_binds:
            decided_by = "aggregate"
        else:
            decided_by = "per_check"

        verdict = Verdict(
            record_id=str(uuid.uuid4()),
            decision=decision,
            records=tuple(records),
            # Only on SCALE: a scale_path on ALLOW/ABSTAIN would mislead.
            scale_path=scale_path if decision is Decision.SCALE else None,
            aggregate_reason=aggregate_reason,
            decided_by=decided_by,
        )
        if self.log is not None:
            # Loud, but not lossy: the verdict is fully formed before the
            # write attempt; on failure it rides out on the error.
            from decision_governor.instrumentation.errors import LogWriteError
            from decision_governor.instrumentation.records import build_record

            describes = {}
            for check in selected:
                describe_fn = getattr(check, "describe", None)
                describes[check.name] = (
                    describe_fn()
                    if callable(describe_fn)
                    else {"name": check.name, "deterministic": check.deterministic}
                )
            try:
                self.log.write(
                    build_record(verdict, self.policy, ctx, self.deployment, describes)
                )
            except Exception as exc:
                raise LogWriteError(verdict, exc) from exc
        return verdict

    def report_outcome(
        self,
        record_id: str,
        ok: bool,
        detail: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Amend the stored record's execution outcome (the system's only
        mutation; provenance, never a recomputation input)."""
        if self.log is None:
            raise NoLogConfigured()
        from decision_governor.instrumentation.outcomes import report_outcome

        return report_outcome(self.log, record_id, ok, detail)


def gate(
    gov: Governor,
    checks: Sequence[str] | None = None,
    scale_path: str | None = None,
    facts: Callable[[Mapping[str, Any]], Any] | None = None,
) -> Callable[[Callable[P, Any]], Callable[P, GateResult]]:
    """Sugar over evaluate() — thin on purpose, so the imperative and
    decorated paths can never diverge.

    `facts` extracts the fact source from the wrapped function's kwargs;
    this is how claims_supported gets its ground truth in G-3 without the
    gate knowing anything about NLI.
    """

    def decorator(fn: Callable[P, Any]) -> Callable[P, GateResult]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> GateResult:
            output = fn(*args, **kwargs)
            context: dict[str, Any] = {"gate": fn.__name__, "kwargs": kwargs}
            if facts is not None:
                context["facts"] = facts(kwargs)
            return GateResult(
                output, gov.evaluate(output, context, scale_path, checks=checks)
            )

        return wrapper

    return decorator
