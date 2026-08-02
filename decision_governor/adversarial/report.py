"""The shared report artifact — Step 1 of Card G-5.

All four tools (injection, shift, cascade, calibration) emit this one
shape, so the CI action, the docs, and the technical report's Section 5
consume a single format. to_json() reuses G-4's canonical serializer, so
adversarial reports inherit the same reproducibility discipline as audit
bundles for free (byte-identical under a fixed seed, safe to archive
alongside a bundle).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from decision_governor.instrumentation.canonical import canonical_bytes, sha256_hex

TOOLS = ("injection", "shift", "cascade", "calibration")


@dataclass(frozen=True)
class AdversarialReport:
    """One tool's result, reproducible from (params, seed).

    metrics is deliberately FLAT and its names are the whitelisted
    vocabulary the CI --fail-on expression reads (see _failon.py); keeping
    the report and the CI vocabulary the same dict is what stops report
    fields from proliferating namelessly.
    """

    tool: str
    seed: int | None                                   # MANDATORY where randomness exists
    params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    judgment: str | None = None                        # the one-line human sentence

    def __post_init__(self) -> None:
        if self.tool not in TOOLS:
            raise ValueError(f"tool must be one of {TOOLS}, got {self.tool!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "seed": self.seed,
            "params": self.params,
            "metrics": self.metrics,
            "findings": self.findings,
            "judgment": self.judgment,
        }

    def to_json(self) -> bytes:
        """Canonical bytes — one recipe, shared with the audit bundle."""
        return canonical_bytes(self.to_dict())

    def digest(self) -> str:
        return sha256_hex(self.to_json())
