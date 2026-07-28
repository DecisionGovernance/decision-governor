"""Check base plumbing: the conveniences every G-3 check leans on."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from decision_governor.core.types import CheckResult


def clamp01(x: float) -> float:
    """No check may emit an out-of-range score, even by bug."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def extract_text(output: Any) -> str:
    """str passes through; objects with a .text attribute contribute it;
    anything else is governed by its str() form (gates govern decisions,
    not documents — the object may be an action)."""
    if isinstance(output, str):
        return output
    text = getattr(output, "text", None)
    if isinstance(text, str):
        return text
    return str(output)


def modality_of(output: Any, context: Mapping[str, Any]) -> str:
    """Return a declared modality without guessing from an opaque payload.

    Outputs declare their own modality first, followed by the deployment's
    ``output_modality`` context value. The built-in text convenience is only
    for the shipped default; undeclared payloads remain ``"unknown"`` so they
    skip safely rather than being guessed into a check.
    """
    declared = getattr(output, "modality", None)
    if isinstance(declared, str):
        return declared
    context_modality = context.get("output_modality")
    if isinstance(context_modality, str):
        return context_modality
    if isinstance(output, str):
        return "text"
    if isinstance(getattr(output, "text", None), str):
        return "text"
    return "unknown"


class CheckBase:
    """Mixin under the frozen Check protocol: name, deterministic flag,
    describe() for the audit bundle's model-pins section, and the skip()
    constructor for checks that don't apply to this output type."""

    name: str = ""
    deterministic: bool = False

    def describe(self) -> dict[str, Any]:
        """This check's configuration, exactly as G-4 will bundle it."""
        return {
            "name": self.name,
            "deterministic": self.deterministic,
            "class": type(self).__name__,
            "config": self._config(),
        }

    def _config(self) -> dict[str, Any]:
        return {}

    def skip(self, reason: str) -> CheckResult:
        """Standardized 'does not apply' result: clean, fully confident,
        with the reason on the record."""
        return CheckResult(score=0.0, confidence=1.0, evidence=[f"n/a: {reason}"])
