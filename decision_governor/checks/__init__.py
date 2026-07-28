"""Built-in G-3 checks and deterministic default registration."""
from __future__ import annotations

from typing import Protocol

from decision_governor.checks import _models, claims
from decision_governor.checks._base import clamp01, extract_text
from decision_governor.checks.claims import ClaimsSupported
from decision_governor.checks.compliance import (
	ChecklistItem,
	evaluate_checklist,
	load_checklist,
	nist_ai_rmf_profile,
)
from decision_governor.checks.domain import OutputDomain
from decision_governor.checks.fairness import ProtectedAttributeLeak
from decision_governor.checks.monitors import verdict_disparity
from decision_governor.checks.pii import PIILeak
from decision_governor.checks.style import StyleDrift
from decision_governor.core.types import Check


class _CheckRegistrar(Protocol):
	def register(self, check: Check) -> None: ...


def default_checks() -> tuple[PIILeak | OutputDomain | ProtectedAttributeLeak, ...]:
	"""The deterministic trio included in every standard text-first gate."""
	return (PIILeak(), OutputDomain(), ProtectedAttributeLeak())


def register_default_checks(governor: _CheckRegistrar) -> None:
	"""Register the deterministic defaults without coupling checks to core."""
	for check in default_checks():
		governor.register(check)


__all__ = [
	"ChecklistItem",
	"ClaimsSupported",
	"OutputDomain",
	"PIILeak",
	"ProtectedAttributeLeak",
	"StyleDrift",
	"_models",
	"claims",
	"clamp01",
	"default_checks",
	"evaluate_checklist",
	"extract_text",
	"load_checklist",
	"nist_ai_rmf_profile",
	"register_default_checks",
	"verdict_disparity",
]
