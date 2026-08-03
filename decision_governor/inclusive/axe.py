"""The axe-core adapter shell — Step 5 of Card G-6, DESCOPED to v0.2.

The pre-authorized timebox decision, taken and recorded here and in
docs/G6-checklist.md: v0.1 ships this degrading shell — it detects
Node.js and skips cleanly with a stated reason either way — and the full
subprocess integration (pipe HTML to a tiny axe-core runner, parse JSON
results back into CheckResult) ships in v0.2. The three native checks in
wcag.py are the floor; axe is the nice-to-have whose absence is
pre-forgiven, and axe-core's rich ruleset is exactly the scope creep the
one-day timebox guards against.

deterministic = True because axe's ruleset is deterministic — when the
adapter is completed, its results remain in the tighten-only stratum
that may support ALLOW.
"""
from __future__ import annotations

import shutil
from collections.abc import Mapping
from typing import Any

from decision_governor.checks._base import CheckBase
from decision_governor.core.types import CheckResult


class AxeCoreCheck(CheckBase):
    """Adapter stub — full axe-core integration in v0.2.

    Registerable today: it degrades to a clean, fully-stated skip, so a
    gate wired for v0.2 works unchanged on v0.1 and simply gains the axe
    ruleset when the adapter is completed.
    """

    name = "axe_core"
    deterministic = True  # axe rules are deterministic

    def __init__(self) -> None:
        self._node = shutil.which("node")

    def _config(self) -> dict[str, Any]:
        return {"node_detected": self._node is not None, "status": "stub — v0.2"}

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult:
        if self._node is None:
            return self.skip(
                "axe-core adapter requires Node.js (not found on PATH); "
                "adapter stub — full axe integration in v0.2"
            )
        return self.skip(
            "axe-core adapter stub — Node.js detected, but the subprocess "
            "runner ships in v0.2 (pre-authorized G-6 descope)"
        )
