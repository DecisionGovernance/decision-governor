"""Card G-7 Steps 2–3 — the LLM-judge adapter (`[llm]` extra).

The card's most safety-sensitive component: it puts a learned model into
the check library, and the system's integrity depends on that model
being treated as learned. Two rules are stated in code, not docs:

1. ``deterministic`` is a READ-ONLY property returning False — not a
   constructor parameter, not an assignable attribute. There is no way
   for a caller to promote the judge into the stratum that can authorize
   ALLOW; it is structurally confined to tighten-only escalation.
2. The constructor REFUSES floating model aliases ("latest", "gpt-4",
   bare family names) with a hard error. "The LLM judge said fine" is
   only reproducible-in-audit if the exact model version is pinned.

Operational rules with the same status: temperature is 0 always (a judge
whose verdicts vary run-to-run is unauditable); the model's response is
parsed DEFENSIVELY (malformed output degrades to a conservative
low-confidence escalation, never a crash); and the full prompt plus raw
response go into evidence, so the audit bundle shows exactly what the
judge was asked and what it said — reasoning, not a black box.

Provider SDKs (`openai`, `anthropic`) are imported lazily inside the
adapters, never at module top: the base install must survive without
them. The OpenAI-compatible adapter's ``base_url`` covers local servers
(vLLM, Ollama), keeping the no-external-keys option alive.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from decision_governor.checks._base import CheckBase, clamp01
from decision_governor.core.types import CheckResult

# Malformed or failed judge output degrades to this: a mild escalation
# with low confidence. The judge told us nothing, so it must not be able
# to look clean — and, being non-deterministic, it cannot authorize
# anything either way.
DEGRADED_SCORE = 1.0
DEGRADED_CONFIDENCE = 0.3

_KNOWN_FLOATING = frozenset({"latest", "stable", "default", "auto"})
# A pin is a dated version suffix (20241022 / 2024-10-22) or a content
# digest (Ollama's name@sha256:... form) — something a registry cannot
# silently repoint.
_DATED = re.compile(r"(?:^|[-_.:@])(20\d{2}-?[01]\d-?[0-3]\d)$")
_DIGEST = re.compile(r"sha256[:-][0-9a-f]{12,64}$")


def is_floating_alias(model: Any) -> bool:
    """True when `model` is not a pinned, dated version string."""
    if not isinstance(model, str) or not model.strip():
        return True
    name = model.strip().lower()
    if name in _KNOWN_FLOATING:
        return True
    if name.endswith(("-latest", ":latest", "@latest")):
        return True
    return not (_DATED.search(name) or _DIGEST.search(name))


@runtime_checkable
class Provider(Protocol):
    """The judge's model seam: one completion call, nothing else."""

    def complete(self, prompt: str, model: str, temperature: float) -> str: ...


def _missing_sdk(package: str) -> ModuleNotFoundError:
    return ModuleNotFoundError(
        f"{package} is not installed. The LLM-judge providers are optional: "
        'install with pip install "decision-governor[llm]".'
    )


class OpenAICompatibleProvider:
    """OpenAI's API and any OpenAI-compatible server (vLLM, Ollama,
    llama.cpp) via `base_url` — the local-server path keeps the
    no-external-keys option alive. A prebuilt `client` may be injected
    (tests, custom transports); otherwise the SDK is imported lazily on
    first use."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any = None,
    ) -> None:
        self.base_url = base_url
        self._api_key = api_key
        self._client = client

    def _resolve_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ModuleNotFoundError as exc:
                raise _missing_sdk("openai") from exc
            self._client = OpenAI(api_key=self._api_key, base_url=self.base_url)
        return self._client

    def complete(self, prompt: str, model: str, temperature: float) -> str:
        response = self._resolve_client().chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


class AnthropicProvider:
    """Anthropic's Messages API. Same lazy-import and injectable-client
    contract as the OpenAI-compatible adapter."""

    def __init__(
        self,
        api_key: str | None = None,
        max_tokens: int = 1024,
        client: Any = None,
    ) -> None:
        self.max_tokens = max_tokens
        self._api_key = api_key
        self._client = client

    def _resolve_client(self) -> Any:
        if self._client is None:
            try:
                from anthropic import Anthropic
            except ModuleNotFoundError as exc:
                raise _missing_sdk("anthropic") from exc
            kwargs = {"api_key": self._api_key} if self._api_key else {}
            self._client = Anthropic(**kwargs)
        return self._client

    def complete(self, prompt: str, model: str, temperature: float) -> str:
        response = self._resolve_client().messages.create(
            model=model,
            max_tokens=self.max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            text for text in (getattr(block, "text", None) for block in response.content)
            if isinstance(text, str)
        )


@dataclass(frozen=True)
class _JudgeVerdict:
    score: float
    confidence: float
    reason: str


def parse_constrained(raw: str) -> _JudgeVerdict | None:
    """Parse the instructed ``{score, confidence, reason}`` JSON out of a
    model response that may not comply: fenced blocks, prose around the
    object, or garbage. None means unparseable — the caller degrades
    conservatively, it never crashes."""
    if not isinstance(raw, str):
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(raw[start : end + 1])
        score = clamp01(float(obj["score"]))
        confidence = clamp01(float(obj["confidence"]))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    return _JudgeVerdict(score, confidence, str(obj.get("reason", "")))


class LLMJudgeCheck(CheckBase):
    """A learned judge under the standard Check protocol.

    Structurally confined: non-deterministic (tighten-only stratum, not
    configurable) and pinned (floating model aliases are a hard error).
    """

    def __init__(
        self,
        name: str,
        provider: Provider,
        model: str,
        prompt_template: str,
    ) -> None:
        if is_floating_alias(model):
            raise ValueError(
                f"model must be a pinned, dated version string, not {model!r}. "
                "A floating alias makes verdicts irreproducible: the audit "
                "bundle would pin a name whose meaning the registry can "
                'change. Use e.g. "claude-3-5-sonnet-20241022", '
                '"gpt-4o-2024-08-06", or a name@sha256:... digest.'
            )
        self.name = name
        self.provider = provider
        self.model = model
        self.template = prompt_template

    # HARDCODED. Not a parameter, not an assignable attribute: a
    # read-only property means no caller — constructor or after — can
    # promote the judge into the stratum that can authorize ALLOW.
    # The [override] suppression is deliberate and narrow: CheckBase
    # declares a writeable `deterministic`, and refusing writes is
    # exactly this class's safety property.
    @property
    def deterministic(self) -> bool:  # type: ignore[override]
        return False

    def _config(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "provider": type(self.provider).__name__,
            "temperature": 0.0,
            "prompt_template_sha256": hashlib.sha256(
                self.template.encode("utf-8")
            ).hexdigest(),
        }

    def _degraded(self, *evidence: str) -> CheckResult:
        """The one conservative degradation path: a mild escalation with
        low confidence and the failure named in evidence — the judge
        told us nothing, so it must not look clean, and it never
        crashes the evaluation."""
        return CheckResult(
            score=DEGRADED_SCORE,
            confidence=DEGRADED_CONFIDENCE,
            evidence=[f"judge={self.model}", *evidence],
        )

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult:
        try:
            prompt = self.template.format(output=output, **context)
        except (AttributeError, IndexError, KeyError, ValueError) as exc:
            # Malformed-but-natural templates (a placeholder the context
            # doesn't carry, a literal JSON example with unescaped
            # braces) must reach the same degradation path as every
            # other judge failure, not crash before a verdict exists.
            return self._degraded(
                f"prompt_template={self.template}",
                (
                    f"template rendering failed ({type(exc).__name__}: {exc}) — "
                    "conservative low-confidence escalation; escape literal braces "
                    "as {{ }} and ensure every placeholder exists in the context"
                ),
            )
        try:
            raw = self.provider.complete(prompt, self.model, temperature=0.0)
        except Exception as exc:  # noqa: BLE001 — a judge outage must degrade, not crash
            return self._degraded(
                f"prompt={prompt}",
                (
                    f"provider call failed ({type(exc).__name__}: {exc}) — "
                    "conservative low-confidence escalation, judge unavailable"
                ),
            )
        parsed = parse_constrained(raw)
        if parsed is None:
            return self._degraded(
                f"prompt={prompt}",
                f"raw_response={raw}",
                (
                    "malformed judge output (no valid {score, confidence, reason} "
                    "JSON) — conservative low-confidence escalation"
                ),
            )
        return CheckResult(
            score=parsed.score,
            confidence=parsed.confidence,
            evidence=[
                f"judge={self.model}",
                f"prompt={prompt}",
                f"raw_response={raw}",
                parsed.reason,
            ],
        )
