"""Card G-6 — the inclusive deployment gate, COMMENCED (timeboxed one day).

Three static, deterministic checks under the standard Check protocol —
alt-text presence, contrast arithmetic on statically-extractable inline
colors, and form-label association — plus a degrading axe-core adapter
shell (full integration: v0.2, pre-authorized descope). This is the
commenced minimal inclusive gate, not a Section 508 conformance claim;
docs/inclusive-roadmap.md states the boundary plainly.
"""
from decision_governor.inclusive.axe import AxeCoreCheck
from decision_governor.inclusive.wcag import (
    AA_NORMAL_TEXT_RATIO,
    AltTextPresence,
    ContrastArithmetic,
    LabelAssociation,
    contrast_ratio,
    parse_css_color,
    relative_luminance,
)

__all__ = [
    "AA_NORMAL_TEXT_RATIO",
    "AltTextPresence",
    "AxeCoreCheck",
    "ContrastArithmetic",
    "LabelAssociation",
    "contrast_ratio",
    "parse_css_color",
    "relative_luminance",
]
