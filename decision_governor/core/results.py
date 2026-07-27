"""The three result shapes, all frozen."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from decision_governor.core.types import CheckResult, Decision


@dataclass(frozen=True)
class CheckRecord:
    """One check's contribution to a verdict, exactly as G-4 will log it."""

    name: str
    deterministic: bool
    result: CheckResult
    decision: Decision


@dataclass(frozen=True)
class Verdict:
    """The engine's answer for one evaluation.

    record_id is a UUID string already, before the G-4 log exists, so
    callers' code doesn't change when the log lands.
    """

    record_id: str
    decision: Decision
    records: tuple[CheckRecord, ...]
    scale_path: str | None = None
    aggregate_reason: str | None = None

    @property
    def reasons(self) -> list[str]:
        """Every non-ALLOW check as a human-readable line with its evidence."""
        lines: list[str] = []
        for r in self.records:
            if r.decision is Decision.ALLOW:
                continue
            evidence = "; ".join(r.result.evidence) if r.result.evidence else "no evidence"
            lines.append(
                f"{r.name} -> {r.decision.value} "
                f"(score={r.result.score:.3f}, confidence={r.result.confidence:.3f}): "
                f"{evidence}"
            )
        if self.aggregate_reason is not None:
            lines.append(self.aggregate_reason)
        return lines


@dataclass(frozen=True)
class GateResult:
    """A gated function's output plus its Verdict.

    decision/reasons/scale_path pass through as conveniences so the
    quickstart reads naturally.
    """

    output: Any
    verdict: Verdict

    @property
    def decision(self) -> Decision:
        return self.verdict.decision

    @property
    def reasons(self) -> list[str]:
        return self.verdict.reasons

    @property
    def scale_path(self) -> str | None:
        return self.verdict.scale_path
