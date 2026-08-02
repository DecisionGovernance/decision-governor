"""The bundled example gate — Step 7 of Card G-5.

A self-contained summarizer gate wired from three deterministic checks —
an injection guard, PII leak (reused from G-3), and a domain guard —
echoing the quickstart. It is the fixture the whole toolkit runs against
for the G-5 gate, and the target the docs' shown report artifact is
generated from:

    python -m decision_governor.adversarial \
        --target decision_governor.adversarial.example:build_example_gate \
        --fail-on "injection_pass < 1.0"

Deterministic on purpose: every check is rule-based, so toolkit runs
against it are reproducible byte-for-byte (given a seed where one is
required) and safe to pin in documentation.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from decision_governor import Governor
from decision_governor.checks._base import extract_text
from decision_governor.checks.pii import PIILeak
from decision_governor.core.types import CheckResult
from decision_governor.risk import CostStructure, CVaRPolicy

_INJECTION_PHRASES = (
    "ignore previous instructions", "ignore all previous", "ignore the above",
    "ignore prior", "disregard all prior", "disregard the above",
    "disregard your instructions", "forget your instructions", "system prompt",
    "reveal your instructions", "reveal your system prompt", "override:",
    "supersedes all", "you are now dan", "developer mode", "jailbreak",
    "unrestricted", "no restrictions", "no limits", "no content policy",
    "without any filter", "pretend you are", "pretend you have", "act as",
    "roleplay as", "freegpt", "credentials", "[inst]", "<system>", "<!--",
    "```system", "forward this", "forward all", "send this", "send the",
    "email this", "email admin", "post to http", "post the", "exfiltrate",
    "redirect the tool", "webhook",
)
_DOMAIN_PHRASES = (
    "buy this stock", "invest in", "returns", "medication", "diagnosis",
    "legal loophole", "evade", "moons", "crypto",
)
_CONTROL_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff", "\u202e")
_HOMOGLYPHS = set("аеосіѕ")  # Cyrillic look-alikes
_BASE64 = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")


def _looks_base64(text: str) -> bool:
    for token in _BASE64.findall(text):
        if any(ch.isdigit() or ch in "+/=" for ch in token):
            return True
    return False


class _KeywordGuard:
    deterministic = True

    def __init__(self, name: str, phrases: tuple[str, ...], scan_specials: bool) -> None:
        self.name = name
        self._phrases = phrases
        self._scan_specials = scan_specials

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult:
        text = extract_text(output)
        low = text.lower()
        hits = [p for p in self._phrases if p in low]
        if self._scan_specials:
            if any(ch in text for ch in _CONTROL_CHARS):
                hits.append("control-char")
            if any(ch in _HOMOGLYPHS for ch in text):
                hits.append("homoglyph")
            if _looks_base64(text):
                hits.append("base64")
        return CheckResult(score=1.0 if hits else 0.0, confidence=1.0, evidence=hits[:5])

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "deterministic": True, "class": "_KeywordGuard"}


def build_example_gate(log: Any = None) -> Governor:
    costs = CostStructure(err=100.0, abstention=3.0)
    policy = CVaRPolicy(alpha=0.05, costs=costs, default_cost="err")
    gov = Governor(policy=policy, log=log, deployment="example-gate")
    gov.register(_KeywordGuard("injection_guard", _INJECTION_PHRASES, scan_specials=True))
    gov.register(PIILeak())
    gov.register(_KeywordGuard("output_domain", _DOMAIN_PHRASES, scan_specials=False))
    return gov
