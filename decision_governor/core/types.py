"""Frozen public contracts — schema_version 1.0, frozen July 25, 2026.

Changes to this module after the freeze are breaking changes and are
treated as such: version bump, changelog entry, migration note.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable


class Decision(str, Enum):
    """The verdict vocabulary of the filed petition, verbatim."""

    ALLOW = "allow"      # execute as proposed
    SCALE = "scale"      # execute in constrained form (per-gate scale_path)
    ABSTAIN = "abstain"  # decline; reasons surfaced to caller

    @property
    def allowed(self) -> bool:
        return self is Decision.ALLOW

    @property
    def scaled(self) -> bool:
        return self is Decision.SCALE


Evidence = str  # v0.1: human-readable span/rule/model reference


@dataclass(frozen=True)
class CheckResult:
    """What every check returns. score: 0 = clean ... 1 = certain violation."""

    score: float
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score must be in [0, 1], got {self.score}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence}")


@runtime_checkable
class Check(Protocol):
    """Anything with a name, a determinism flag, and run() is a check.

    `output` is Any, not str: gates govern decisions, not documents --
    the agent example gates a ToolCall object through this same protocol.
    `deterministic` governs tighten-only treatment in composition:
    only deterministic-clean results may support ALLOW.
    """

    name: str
    deterministic: bool

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult: ...
