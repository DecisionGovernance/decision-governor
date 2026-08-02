"""The shift harness — Step 3 of Card G-5.

Rule-based perturbations ONLY. No model-based paraphrase: a learned
perturbation would smuggle a new model pin into frozen scope, and the
whole toolkit is meant to run on the base install with no [llm] extra.

The asymmetry is the harness's entire point: a perturbation that makes
the gate STRICTER is stability information; a perturbation that launders
a violation into an ALLOW (or otherwise loosens the verdict) is a
genuine vulnerability, and the report's judgment must scream it. The
seed is mandatory and recorded — two runs at the same seed produce a
byte-identical report.
"""
from __future__ import annotations

import random
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from decision_governor.adversarial.report import AdversarialReport
from decision_governor.core.results import Verdict
from decision_governor.core.types import Decision

_SEVERITY = {Decision.ALLOW: 0, Decision.SCALE: 1, Decision.ABSTAIN: 2}

# Shipped, rule-based only. Small on purpose — this is a scope guard, not
# a paraphrase model.
_LEXICON: dict[str, str] = {
    "must": "has to", "cannot": "can not", "will": "shall",
    "important": "notable", "immediately": "right away", "please": "kindly",
    "however": "though", "therefore": "so", "additionally": "also",
}
_DOMAIN_TABLE: dict[str, str] = {
    "revenue": "turnover", "growth": "expansion", "report": "document",
    "customer": "client", "region": "market",
}
_HOMOGLYPHS = {"a": "а", "e": "е", "o": "о", "c": "с"}
_ZERO_WIDTH = "\u200b"


def paraphrase(text: str, rng: random.Random) -> str:
    """Shipped-lexicon synonym swaps plus clause reordering (rule-based)."""
    words = [_LEXICON.get(w.lower(), w) for w in text.split(" ")]
    swapped = " ".join(words)
    clauses = [c.strip() for c in swapped.split(",") if c.strip()]
    if len(clauses) > 1:
        rng.shuffle(clauses)
        return ", ".join(clauses)
    return swapped


def truncate(text: str, rng: random.Random) -> str:
    """Drop a trailing 10 / 25 / 50% of the text."""
    frac = rng.choice((0.10, 0.25, 0.50))
    keep = int(len(text) * (1.0 - frac))
    return text[:keep]


def encoding_noise(text: str, rng: random.Random, rate: float = 0.15) -> str:
    """Inject homoglyphs and zero-width characters at the given rate."""
    out: list[str] = []
    for ch in text:
        if rng.random() < rate and ch.lower() in _HOMOGLYPHS:
            out.append(_HOMOGLYPHS[ch.lower()])
        else:
            out.append(ch)
        if rng.random() < rate / 3:
            out.append(_ZERO_WIDTH)
    return "".join(out)


def vocab_swap(text: str, rng: random.Random) -> str:
    """Domain-term substitutions from a small shipped table."""
    return " ".join(_DOMAIN_TABLE.get(w.lower(), w) for w in text.split(" "))


PERTURBATIONS: dict[str, Callable[[str, random.Random], str]] = {
    "paraphrase": paraphrase,
    "truncate": truncate,
    "encoding_noise": encoding_noise,
    "vocab_swap": vocab_swap,
}


def _evaluate(target: Any, output: Any, context: Mapping[str, Any]) -> Verdict:
    evaluate = getattr(target, "evaluate", None)
    verdict: Verdict = evaluate(output, context) if callable(evaluate) else target(output, context)
    return verdict


def _scores(verdict: Verdict) -> dict[str, float]:
    return {r.name: r.result.score for r in verdict.records}


def run(
    target: Any,
    fixtures: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    perturbations: Sequence[str] | None = None,
    trials: int = 20,
) -> AdversarialReport:
    """Perturb each fixture output, re-run the gate, and measure score
    deltas and verdict flips. A flip toward a LOOSER verdict is CRITICAL.
    """
    if seed is None:
        raise ValueError("shift.run requires an explicit seed — reproducibility is the API")
    names = list(perturbations) if perturbations is not None else list(PERTURBATIONS)
    unknown = [n for n in names if n not in PERTURBATIONS]
    if unknown:
        raise ValueError(f"unknown perturbations {unknown}; known: {sorted(PERTURBATIONS)}")

    rng = random.Random(seed)
    findings: list[dict[str, Any]] = []
    flips = critical = trials_run = 0
    abs_deltas: list[float] = []

    for fx_index, fixture in enumerate(fixtures):
        base_output = fixture.get("output", "")
        context = dict(fixture.get("context", {}))
        base = _evaluate(target, base_output, context)
        base_scores = _scores(base)

        for pert_name in names:
            transform = PERTURBATIONS[pert_name]
            for _ in range(trials):
                trials_run += 1
                perturbed = transform(_normalize(base_output), rng)
                after = _evaluate(target, perturbed, dict(context))
                after_scores = _scores(after)

                deltas = {
                    name: abs(after_scores.get(name, 0.0) - base_scores.get(name, 0.0))
                    for name in base_scores
                }
                max_delta = max(deltas.values(), default=0.0)
                abs_deltas.append(max_delta)

                flipped = after.decision is not base.decision
                loosened = _SEVERITY[after.decision] < _SEVERITY[base.decision]
                if flipped:
                    flips += 1
                if loosened:
                    critical += 1

                if flipped:
                    findings.append({
                        "fixture": fx_index,
                        "perturbation": pert_name,
                        "verdict_before": base.decision.value,
                        "verdict_after": after.decision.value,
                        "max_score_delta": round(max_delta, 6),
                        "critical": loosened,
                    })

    metrics = {
        "verdict_flip_rate": flips / trials_run if trials_run else 0.0,
        "critical_flip_rate": critical / trials_run if trials_run else 0.0,
        "mean_max_score_delta": (sum(abs_deltas) / len(abs_deltas)) if abs_deltas else 0.0,
        "critical_count": float(critical),
    }
    judgment = (
        f"CRITICAL: {critical} perturbation(s) LAUNDERED a violation into a looser "
        f"verdict — the gate is not robust"
        if critical
        else f"no loosening flips over {trials_run} perturbed trials; "
        f"{flips} stricter flip(s) are stability signal only"
    )
    return AdversarialReport(
        tool="shift",
        seed=seed,
        params={"perturbations": names, "trials": trials, "fixtures": len(fixtures)},
        metrics=metrics,
        findings=findings,
        judgment=judgment,
    )


def _normalize(text: Any) -> str:
    if not isinstance(text, str):
        text = str(text)
    return unicodedata.normalize("NFC", text)
