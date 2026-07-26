"""Policy protocol and the hand-checkable reference policy.

Division of labor, kept crisp: a policy judges *one* check result; the
engine owns composition. That boundary is what lets CVaRPolicy (G-2)
swap in later without touching the engine.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from decision_governor.core.types import CheckResult, Decision


@runtime_checkable
class Policy(Protocol):
    """Anything with judge() is a policy."""

    def judge(
        self, check_name: str, result: CheckResult, context: Mapping[str, Any]
    ) -> Decision: ...


@dataclass(frozen=True)
class ThresholdPolicy:
    """risk = score * confidence, judged against two fixed thresholds.

    Not a throwaway: the arithmetic is checkable in your head, which keeps
    the engine's property tests legible, and zero-dependency users get a
    sane default.
    """

    scale_at: float = 0.25
    abstain_at: float = 0.60

    def __post_init__(self) -> None:
        if not 0.0 <= self.scale_at <= self.abstain_at <= 1.0:
            raise ValueError(
                "ThresholdPolicy requires 0 <= scale_at <= abstain_at <= 1, got "
                f"scale_at={self.scale_at}, abstain_at={self.abstain_at}."
            )

    def judge(
        self, check_name: str, result: CheckResult, context: Mapping[str, Any]
    ) -> Decision:
        risk = result.score * result.confidence
        if risk >= self.abstain_at:
            return Decision.ABSTAIN
        if risk >= self.scale_at:
            return Decision.SCALE
        return Decision.ALLOW
