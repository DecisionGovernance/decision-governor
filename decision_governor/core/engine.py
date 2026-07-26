"""Card G-1: the Governor, decision composition, and the @gate decorator.

Composition guarantees (proved by property tests, not asserted):
deterministic, order-invariant, and tighten-only. The consequence, read
out loud: a learned component can be the reason an action was
*constrained*, never the reason one was *authorized*.
"""
from __future__ import annotations

import functools
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any, ParamSpec

from decision_governor.core.errors import InvalidPolicy, NoChecksRegistered, UnknownCheck
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
        self.log = log  # accepted and held unused: the G-4 seam, pre-cut
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

        decision = _compose(records)
        return Verdict(
            record_id=str(uuid.uuid4()),
            decision=decision,
            records=tuple(records),
            # Only on SCALE: a scale_path on ALLOW/ABSTAIN would mislead.
            scale_path=scale_path if decision is Decision.SCALE else None,
        )


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
