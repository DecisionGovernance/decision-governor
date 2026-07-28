"""The compliance family: a deliberately simple checklist runner plus
the shipped NIST AI RMF profile.

Items map either to an SDK capability (check_type: automated) or to a
deployment attestation (check_type: attested). The evaluator produces a
coverage report; the honesty of the not_covered rows is what makes the
covered rows credible.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# Capabilities that exist in the codebase TODAY. decision_logging and the
# adversarial toolkit are deliberately absent until G-4/G-5 land — profile
# rows mapping to them render not_covered until the capability is real.
SDK_CAPABILITIES: frozenset[str] = frozenset(
    {
        "tighten_only_composition",
        "deterministic_verdicts",
        "cvar_policy",
        "cost_structures",
        "credibility_estimation",
        "dynamic_thresholds",
        "pii_leak_check",
        "output_domain_check",
        "protected_attribute_leak_check",
        "style_drift_check",
        "claims_supported_check",
        "verdict_disparity_monitor",
        "model_pinning",
        "audit_reasons",
    }
)

_VALID_CHECK_TYPES = ("automated", "attested")


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    requirement: str
    check_type: str                 # "automated" | "attested"
    capability: str | None = None   # automated: the SDK capability name

    def __post_init__(self) -> None:
        if self.check_type not in _VALID_CHECK_TYPES:
            raise ValueError(
                f"item {self.id!r}: check_type must be one of "
                f"{_VALID_CHECK_TYPES}, got {self.check_type!r}"
            )
        if self.check_type == "automated" and not self.capability:
            raise ValueError(
                f"item {self.id!r}: automated items must name the SDK "
                "capability they map to."
            )


@dataclass(frozen=True)
class CoverageReport:
    covered: tuple[ChecklistItem, ...]
    attested: tuple[ChecklistItem, ...]
    not_covered: tuple[ChecklistItem, ...]

    @property
    def total(self) -> int:
        return len(self.covered) + len(self.attested) + len(self.not_covered)

    @property
    def coverage(self) -> float:
        if self.total == 0:
            return 0.0
        return (len(self.covered) + len(self.attested)) / self.total

    @property
    def lines(self) -> list[str]:
        out: list[str] = []
        for label, items in (
            ("covered", self.covered),
            ("attested", self.attested),
            ("not_covered", self.not_covered),
        ):
            for item in items:
                via = f" via {item.capability}" if item.capability else ""
                out.append(f"[{label}] {item.id}: {item.requirement}{via}")
        out.append(
            f"coverage: {len(self.covered)} automated + {len(self.attested)} "
            f"attested of {self.total} ({self.coverage:.0%})"
        )
        return out


def evaluate_checklist(
    items: Sequence[ChecklistItem],
    capabilities: frozenset[str] = SDK_CAPABILITIES,
    attestations: Mapping[str, bool] | None = None,
) -> CoverageReport:
    """automated + capability present -> covered; attested + a truthy
    deployment attestation -> attested; everything else -> not_covered,
    stated plainly."""
    attestations = attestations or {}
    covered: list[ChecklistItem] = []
    attested: list[ChecklistItem] = []
    missing: list[ChecklistItem] = []
    for item in items:
        if item.check_type == "automated" and item.capability in capabilities:
            covered.append(item)
        elif item.check_type == "attested" and attestations.get(item.id):
            attested.append(item)
        else:
            missing.append(item)
    return CoverageReport(tuple(covered), tuple(attested), tuple(missing))


def load_checklist(path: str | Path) -> list[ChecklistItem]:
    """Load a YAML or JSON checklist file: a list of item mappings."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        import yaml

        raw = yaml.safe_load(text)
    else:
        raw = json.loads(text)
    if not isinstance(raw, list):
        raise TypeError(
            f"{path}: a checklist file must contain a list of items, "
            f"got {type(raw).__name__}."
        )
    return [
        ChecklistItem(
            id=str(entry["id"]),
            requirement=str(entry["requirement"]),
            check_type=str(entry["check_type"]),
            capability=entry.get("capability"),
        )
        for entry in raw
    ]


def nist_ai_rmf_profile() -> list[ChecklistItem]:
    """The shipped NIST AI RMF profile (Govern/Map/Measure/Manage)."""
    return load_checklist(Path(__file__).parent / "profiles" / "nist_ai_rmf.yaml")
