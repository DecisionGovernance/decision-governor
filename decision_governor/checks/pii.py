"""pii_leak: deterministic safety check. Pattern battery plus dictionary.

Evidence is the MASKED matched span — the check must never itself
reproduce the PII it caught into the log.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from re import Pattern
from typing import Any

from decision_governor.checks._base import CheckBase, extract_text
from decision_governor.core.types import CheckResult

_PATTERNS: list[tuple[str, Pattern[str]]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    # US phone: separators required, so plain numbers and years don't match.
    ("phone", re.compile(
        r"(?<![\d.])(?:\+?1[\s.-])?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"
    )),
    # International: +country code then grouped digits.
    ("phone", re.compile(
        r"(?<![\d.])\+(?!1[\s.-])\d{1,3}[\s.-]?\d{2,4}[\s.-]\d{2,4}(?:[\s.-]\d{2,4})?(?!\d)"
    )),
    ("ssn", re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")),
    ("address", re.compile(
        r"\b\d{1,5}\s+\w+(?:\s\w+)?\s+"
        r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|"
        r"Lane|Ln\.?|Drive|Dr\.?)\b",
        re.IGNORECASE,
    )),
]


def _mask(category: str, span: str) -> str:
    if category == "email" and "@" in span:
        local, _, domain = span.partition("@")
        tld = domain[domain.rfind("."):] if "." in domain else ""
        return f"{local[:1]}***@***{tld}"
    # Everything else: last two characters only.
    return f"***{span[-2:]}"


class PIILeak(CheckBase):
    """Emails, phone formats (US and international), SSN-shaped strings,
    physical-address heuristics, and a configurable custom-terms list
    (the user's own sensitive strings). PII is binary: present or not."""

    name = "pii_leak"
    deterministic = True

    def __init__(self, custom_terms: Sequence[str] = ()) -> None:
        self._custom_terms = tuple(custom_terms)

    def _config(self) -> dict[str, Any]:
        return {
            "patterns": sorted({label for label, _ in _PATTERNS}),
            # Configuration ships masked too: the terms are themselves PII.
            "custom_terms": [_mask("custom", t) for t in self._custom_terms],
        }

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult:
        text = extract_text(output)
        hits: list[str] = []
        for category, pattern in _PATTERNS:
            for match in pattern.finditer(text):
                hits.append(
                    f"{category}: {_mask(category, match.group())} "
                    f"at offset {match.start()}"
                )
        terms = list(self._custom_terms) + list(context.get("custom_terms", ()))
        for term in terms:
            for match in re.finditer(re.escape(term), text, re.IGNORECASE):
                hits.append(
                    f"custom-term: {_mask('custom', match.group())} "
                    f"at offset {match.start()}"
                )
        return CheckResult(
            score=1.0 if hits else 0.0, confidence=1.0, evidence=hits
        )
