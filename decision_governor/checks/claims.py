"""claims_supported: non-deterministic safety check — the hardest
function in the SDK. Four stages, each independently testable:
segment -> detect claims -> retrieve nearest facts -> NLI entailment.

Design decisions, made deliberately:

- Claim detection (v0.1) uses cheap heuristics: declarative sentences
  containing first-person voice AND verifiable content (numbers, dates,
  titles, named entities, achievement verbs); pure opinion/aspiration
  sentences are skipped. Over-detection is the SAFE failure (a non-claim
  tested against facts lands neutral and gets caught by review);
  under-detection is the dangerous one — the heuristics are biased
  toward over-detection on purpose.
- Neutral is not innocent: an unsupported claim isn't a contradicted
  one, but it is still a fabrication risk — hence weight 0.6, not 0.
- Worst-claim-wins (max, not mean): the same non-substitutability logic
  as the engine's composition, one level down.
- Retrieval-before-NLI (top-k facts as premise) because NLI models
  degrade with long premises. This is miniature RAG, and the retrieved
  facts going into evidence is what makes review-queue highlighting work.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

from decision_governor.checks import _models
from decision_governor.checks._base import CheckBase, clamp01, extract_text, modality_of
from decision_governor.checks._models import DEFAULT_TEXT_EMBEDDER, Embedder
from decision_governor.core.types import CheckResult

# nli(premise, hypothesis) -> (label, probability); label in
# {"entailed", "neutral", "contradicted"}.
NLIFn = Callable[[str, str], tuple[str, float]]

WEIGHTS = {"contradicted": 1.0, "neutral": 0.6, "entailed": 0.0}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_OPINION = re.compile(
    r"^\s*(?:i\s+(?:believe|hope|feel|think|would love|am excited|"
    r"look forward)|my\s+(?:passion|dream|goal)\b)",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(r"\b(?:i|my|we|our|me)\b", re.IGNORECASE)
_VERIFIABLE = re.compile(
    r"\d|%|\b(?:led|managed|built|created|launched|delivered|increased|"
    r"reduced|founded|shipped|promoted|certified|awarded|degree|team|"
    r"january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\b"
    r"|\b[A-Z][a-z]+\s+[A-Z][a-z]+\b",
    re.IGNORECASE,
)


def segment(text: str) -> list[str]:
    """Regex sentence segmentation (v0.1; pysbd is a documented upgrade
    path, not a dependency)."""
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def is_claim(sentence: str) -> bool:
    """Declarative + first-person + verifiable content; skips pure
    opinion/aspiration. Biased toward over-detection — see module doc."""
    if sentence.endswith("?"):
        return False
    if _OPINION.match(sentence):
        return False
    return bool(_FIRST_PERSON.search(sentence)) and bool(_VERIFIABLE.search(sentence))


def normalize_facts(facts: Any) -> list[str]:
    if isinstance(facts, str):
        return segment(facts)
    return [str(f).strip() for f in facts if str(f).strip()]


class ClaimsSupported(CheckBase):
    """Every detected claim is tested for entailment against its top-k
    nearest facts; the worst claim sets the score, and the NLI model's
    own probability on that deciding claim sets the confidence."""

    name = "claims_supported"
    deterministic = False

    TOP_K = 3

    def __init__(
        self,
        nli: NLIFn | None = None,
        embedder: Embedder = DEFAULT_TEXT_EMBEDDER,
        top_k: int = TOP_K,
    ) -> None:
        # Non-injected backends must be usable, or fail loud NOW rather
        # than mid-evaluation (unfrozen-pin descope, G-3 record).
        if nli is None:
            _models.require_default_backend("nli")
        if embedder is DEFAULT_TEXT_EMBEDDER:
            _models.require_default_backend("embedding")
        self._nli = nli
        self.embedder = embedder
        self.top_k = top_k

    def _config(self) -> dict[str, Any]:
        from decision_governor.checks import _models

        return {
            "top_k": self.top_k,
            "weights": dict(WEIGHTS),
            "nli_model": "injected" if self._nli else _models.describe("nli"),
            "embedder": self.embedder.describe(),
        }

    # -- model access (injected in tests, pinned in production) ----------

    def _embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.embedder.embed(texts), dtype=float)

    def _entail(self, premise: str, hypothesis: str) -> tuple[str, float]:
        if self._nli is not None:
            return self._nli(premise, hypothesis)
        from decision_governor.checks import _models

        outputs = _models.load("nli")({"text": premise, "text_pair": hypothesis})
        best = max(outputs[0], key=lambda o: o["score"]) if isinstance(
            outputs[0], list
        ) else max(outputs, key=lambda o: o["score"])
        label = {"entailment": "entailed", "contradiction": "contradicted"}.get(
            best["label"].lower(), "neutral"
        )
        return label, float(best["score"])

    def _nearest_facts(
        self, claim_vector: np.ndarray, facts: list[str], fact_vectors: np.ndarray
    ) -> list[str]:
        norms = np.linalg.norm(fact_vectors, axis=1) * np.linalg.norm(claim_vector)
        norms = np.where(norms == 0, 1e-12, norms)
        similarity = fact_vectors @ claim_vector / norms
        top = np.argsort(similarity)[::-1][: min(self.top_k, len(facts))]
        return [facts[i] for i in top]

    # -- the four stages -------------------------------------------------

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult:
        output_modality = modality_of(output, context)
        if output_modality != "text" or self.embedder.modality != "text":
            return self.skip(
                f"output modality {output_modality!r} or embedder modality "
                f"{self.embedder.modality!r} is not text"
            )
        raw_facts = context.get("facts")
        if not raw_facts:
            return self.skip("no facts provided in context['facts']")
        facts = normalize_facts(raw_facts)
        if not facts:
            return self.skip("context['facts'] normalized to nothing")

        text = extract_text(output)
        claims = [s for s in segment(text) if is_claim(s)]
        if not claims:
            return CheckResult(
                score=0.0, confidence=1.0,
                evidence=["no verifiable claims detected"],
            )

        vectors = self._embed(facts + claims)
        fact_vectors, claim_vectors = vectors[: len(facts)], vectors[len(facts):]

        evidence: list[str] = []
        worst_score = 0.0
        deciding_prob = 1.0
        for claim, claim_vector in zip(claims, claim_vectors):
            nearest = self._nearest_facts(claim_vector, facts, fact_vectors)
            label, prob = self._entail(" ".join(nearest), claim)
            weighted = WEIGHTS[label] * prob
            evidence.append(
                f"'{claim}' -> {label.upper()} {prob:.2f} "
                f"(nearest facts: '{'; '.join(nearest)}')"
            )
            if weighted > worst_score or (worst_score == 0.0 and label == "entailed"):
                deciding_prob = prob
            worst_score = max(worst_score, weighted)

        return CheckResult(
            score=clamp01(worst_score),
            confidence=deciding_prob,
            evidence=evidence,
        )
