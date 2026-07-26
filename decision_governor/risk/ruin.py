"""Cramer-Lundberg governance-surplus tracking. PRE-DESCOPED to v0.2.

Interface frozen now so the roadmap is visible in code; implementation
intentionally absent. See the technical report, 'specified future work'.
"""
from __future__ import annotations


class GovernanceSurplus:
    """A budget of tolerable harm; bad ALLOW decisions are claims against it."""

    def __init__(self, initial_surplus: float) -> None:  # pragma: no cover
        raise NotImplementedError("v0.2 -- see roadmap")
