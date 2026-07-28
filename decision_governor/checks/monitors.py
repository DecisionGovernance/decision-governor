"""verdict_disparity: a fairness MONITOR, not a gate — it reads the
decision log, not an output. Per-cohort constrained (ABSTAIN/SCALE)
rates, rate gaps, chi-squared with its p-value, and credibility-weighted
rates so three-member cohorts don't scream false alarms.

Registers with instrumentation's monitoring hook (the G-4 seam), not
with gates.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from decision_governor.core.types import Decision
from decision_governor.risk.credibility import buhlmann_straub


@dataclass(frozen=True)
class CohortStats:
    cohort: str
    n: int
    constrained: int            # ABSTAIN or SCALE verdicts
    constrained_rate: float
    abstain_rate: float
    scale_rate: float
    credibility_rate: float     # Bühlmann–Straub shrunk constrained rate
    Z: float                    # its credibility factor, always visible


@dataclass(frozen=True)
class DisparityReport:
    cohorts: tuple[CohortStats, ...]
    rate_gap: float             # max - min credibility-weighted rate
    chi2: float
    dof: int
    p_value: float
    alpha: float
    flagged: bool

    @property
    def lines(self) -> list[str]:
        out = [
            f"{c.cohort}: n={c.n} constrained={c.constrained_rate:.3f} "
            f"(credibility-weighted {c.credibility_rate:.3f}, Z={c.Z:.2f})"
            for c in self.cohorts
        ]
        out.append(
            f"gap={self.rate_gap:.3f} chi2={self.chi2:.3f} (dof={self.dof}) "
            f"p={self.p_value:.4f} -> "
            + ("DISPARITY FLAGGED" if self.flagged else "no significant disparity")
        )
        return out


def _decision_value(decision: object) -> str:
    if isinstance(decision, Decision):
        return decision.value
    return str(decision).lower()


def verdict_disparity(
    records: Sequence[tuple[str, object]], alpha: float = 0.05
) -> DisparityReport:
    """records: (cohort_label, decision) pairs from the decision log.
    Flags when the chi-squared test on constrained-vs-allowed counts
    across cohorts is significant at `alpha`."""
    if not records:
        raise ValueError(
            "verdict_disparity needs at least one (cohort, decision) record."
        )
    counts: dict[str, dict[str, int]] = {}
    for cohort, decision in records:
        value = _decision_value(decision)
        bucket = counts.setdefault(cohort, {"n": 0, "abstain": 0, "scale": 0})
        bucket["n"] += 1
        if value in ("abstain", "scale"):
            bucket[value] += 1

    credibility = buhlmann_straub(
        {c: (b["n"], b["abstain"] + b["scale"]) for c, b in counts.items()}
    )

    stats = tuple(
        CohortStats(
            cohort=cohort,
            n=b["n"],
            constrained=b["abstain"] + b["scale"],
            constrained_rate=(b["abstain"] + b["scale"]) / b["n"],
            abstain_rate=b["abstain"] / b["n"],
            scale_rate=b["scale"] / b["n"],
            credibility_rate=credibility[cohort].rate,
            Z=credibility[cohort].Z,
        )
        for cohort, b in sorted(counts.items())
    )

    chi2, dof, p = _chi2_contingency(
        [(c.constrained, c.n - c.constrained) for c in stats]
    )
    rates = [c.credibility_rate for c in stats]
    return DisparityReport(
        cohorts=stats,
        rate_gap=max(rates) - min(rates),
        chi2=chi2,
        dof=dof,
        p_value=p,
        alpha=alpha,
        flagged=p < alpha,
    )


def _chi2_contingency(rows: Sequence[tuple[int, int]]) -> tuple[float, int, float]:
    """Pearson chi-squared over a k x 2 (constrained, allowed) table."""
    k = len(rows)
    total = sum(a + b for a, b in rows)
    col_constrained = sum(a for a, _ in rows)
    col_allowed = total - col_constrained
    dof = max(k - 1, 1)
    if k < 2 or col_constrained == 0 or col_allowed == 0 or total == 0:
        return 0.0, dof, 1.0  # degenerate table: no evidence of disparity
    chi2 = 0.0
    for constrained, allowed in rows:
        n_row = constrained + allowed
        for observed, col_total in ((constrained, col_constrained), (allowed, col_allowed)):
            expected = n_row * col_total / total
            if expected > 0:
                chi2 += (observed - expected) ** 2 / expected
    return chi2, dof, chi2_sf(chi2, dof)


# --- chi-squared survival function without scipy (base install is
# --- numeric-only): regularized upper incomplete gamma Q(df/2, x/2).


def chi2_sf(x: float, df: int) -> float:
    if x <= 0.0:
        return 1.0
    return _gammq(df / 2.0, x / 2.0)


def _gammq(a: float, x: float) -> float:
    if x < a + 1.0:
        return max(0.0, min(1.0, 1.0 - _gser(a, x)))
    return max(0.0, min(1.0, _gcf(a, x)))


def _gser(a: float, x: float, itmax: int = 300, eps: float = 3e-10) -> float:
    ap = a
    total = 1.0 / a
    delta = total
    for _ in range(itmax):
        ap += 1.0
        delta *= x / ap
        total += delta
        if abs(delta) < abs(total) * eps:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a: float, x: float, itmax: int = 300, eps: float = 3e-10) -> float:
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, itmax + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


# Monitor registry: instrumentation's monitoring hook (G-4) consumes
# this; gates never do.
MonitorFn = Callable[..., DisparityReport]
MONITORS: Mapping[str, MonitorFn] = {"verdict_disparity": verdict_disparity}
