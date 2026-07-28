"""style_drift: non-deterministic safety check.

Raw cosine distance is not a violation probability, so the score is
calibrated against the user's OWN within-reference variance: how much
their samples differ from each other is the baseline, and the output is
scored by where it falls relative to that. Confidence scales with
reference-sample count — three writing samples can't support strong
claims (credibility-thinking applied inside a check).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from decision_governor.checks import _models
from decision_governor.checks._base import CheckBase, clamp01, modality_of
from decision_governor.checks._models import DEFAULT_TEXT_EMBEDDER, Embedder
from decision_governor.core.types import CheckResult


def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 1.0
    return 1.0 - float(np.dot(a, b)) / denom


class StyleDrift(CheckBase):
    """Distance from the centroid of context["style_refs"], scored
    against the references' own spread (mean ± MAD). v0.1 note: refs are
    compared to their own centroid, not leave-one-out — slightly
    optimistic baseline, documented rather than hidden."""

    name = "style_drift"
    deterministic = False

    MIN_REFS = 5
    K_MAD = 3.0

    def __init__(
        self,
        embedder: Embedder = DEFAULT_TEXT_EMBEDDER,
        min_refs: int = MIN_REFS,
        k_mad: float = K_MAD,
    ) -> None:
        if embedder is DEFAULT_TEXT_EMBEDDER:
            # Not injected: the shipped default must be usable, or fail
            # loud NOW rather than mid-evaluation (unfrozen-pin descope).
            _models.require_default_backend("embedding")
        self.embedder = embedder
        self.min_refs = min_refs
        self.k_mad = k_mad

    def _config(self) -> dict[str, Any]:
        return {
            "min_refs": self.min_refs,
            "k_mad": self.k_mad,
            "embedder": self.embedder.describe(),
        }

    def _embed(self, items: list[Any]) -> np.ndarray:
        return np.asarray(self.embedder.embed(items), dtype=float)

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult:
        output_modality = modality_of(output, context)
        if output_modality != self.embedder.modality:
            # A learned-only gate with this skip has no deterministic evidence;
            # the engine's composition ceiling therefore makes ALLOW unreachable.
            return self.skip(
                f"output modality {output_modality!r} != embedder modality "
                f"{self.embedder.modality!r}"
            )
        refs = list(context.get("style_refs", ()))
        if not refs:
            return self.skip("no style references supplied")
        if len(refs) < 2:
            return self.skip("need at least 2 style_refs for a personal baseline")
        vectors = self._embed(list(refs) + [output])
        ref_vectors, out_vector = vectors[:-1], vectors[-1]
        centroid = ref_vectors.mean(axis=0)

        baseline = np.array(
            [_cosine_distance(v, centroid) for v in ref_vectors], dtype=float
        )
        base_mean = float(baseline.mean())
        # Mean absolute deviation: median-based MAD collapses to 0 for the
        # tiny reference sets this check must serve (3-5 samples).
        mad = float(np.abs(baseline - base_mean).mean())
        spread = max(mad, 1e-9)  # identical refs: any excess distance saturates

        d = _cosine_distance(out_vector, centroid)
        score = clamp01((d - base_mean) / (self.k_mad * spread))
        confidence = min(1.0, len(refs) / self.min_refs)
        return CheckResult(
            score=score,
            confidence=confidence,
            evidence=[
                (
                    f"distance {d:.2f} vs personal baseline "
                    f"{base_mean:.2f}±{mad:.2f} ({len(refs)} reference samples)"
                )
            ],
        )
