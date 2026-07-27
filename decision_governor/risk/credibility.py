"""Bühlmann–Straub credibility: small-sample failure rates, shrunk
toward the collective.

The non-negotiable design rule: the factors ship in the output object —
an auditor sees Z = n/(n+k) with its ingredients (n, k, the collective
mean, the raw rate), never a bare number.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class CredibilityEstimate:
    """A credibility-weighted failure rate with every factor visible."""

    context: str
    rate: float                 # Z * raw_rate + (1 - Z) * collective_mean
    Z: float                    # credibility factor n / (n + k)
    n: int                      # trials observed for this context
    failures: int               # failures observed for this context
    raw_rate: float | None      # failures / n, or None with no observations
    k: float                    # credibility coefficient s^2 / a (inf if a = 0)
    collective_mean: float      # m, the pooled failure rate
    degenerate: bool = False    # single context: no between-variance exists


def buhlmann_straub(
    observations: Mapping[str, tuple[int, int]],
) -> dict[str, CredibilityEstimate]:
    """Per-context failure-rate estimates from {context: (trials, failures)}.

    Standard Bühlmann–Straub moment estimators:
    m = pooled mean; s^2 = weighted average of per-context binomial
    variance; a = between-context variance beyond sampling noise
    (floored at 0); k = s^2 / a; Z_i = n_i / (n_i + k).

    Deliberate edge cases: a context with zero observations gets Z = 0
    and the collective mean, stated as such; a ~ 0 (contexts
    indistinguishable) sends k to infinity and everyone to the
    collective mean; a single context has no between-variance, so its
    raw rate returns flagged Z = 1, degenerate=True.
    """
    if not observations:
        raise ValueError(
            "buhlmann_straub needs at least one context: pass "
            "{context: (trials, failures)} with trials > 0 somewhere."
        )
    for ctx, (n, x) in observations.items():
        if n < 0 or x < 0 or x > n:
            raise ValueError(
                f"context {ctx!r} has (trials={n}, failures={x}); "
                "require 0 <= failures <= trials."
            )
    total_n = sum(n for n, _ in observations.values())
    total_x = sum(x for _, x in observations.values())
    if total_n == 0:
        raise ValueError(
            "no observations in any context: at least one context needs "
            "trials > 0 before credibility can be estimated."
        )
    m = total_x / total_n
    raw: float | None

    if len(observations) == 1:
        ((ctx, (n, x)),) = observations.items()
        raw = x / n
        return {
            ctx: CredibilityEstimate(
                context=ctx, rate=raw, Z=1.0, n=n, failures=x, raw_rate=raw,
                k=math.nan, collective_mean=m, degenerate=True,
            )
        }

    with_data = {c: (n, x) for c, (n, x) in observations.items() if n > 0}
    rates = {c: x / n for c, (n, x) in with_data.items()}

    # Within: weighted average of per-context binomial variance p(1-p).
    s2 = sum(n * rates[c] * (1.0 - rates[c]) for c, (n, _) in with_data.items()) / total_n

    # Between: the standard moment estimator, floored at 0.
    weighted_sq_dev = sum(n * (rates[c] - m) ** 2 for c, (n, _) in with_data.items())
    n_contexts = len(with_data)
    denom = total_n - sum(n * n for n, _ in with_data.values()) / total_n
    if denom <= 0:
        a = 0.0
    else:
        a = max(0.0, (weighted_sq_dev - (n_contexts - 1) * s2) / denom)

    k = math.inf if a == 0.0 else s2 / a

    estimates: dict[str, CredibilityEstimate] = {}
    for ctx, (n, x) in observations.items():
        if n == 0:
            z, raw, rate = 0.0, None, m  # no data: the collective mean, stated as such
        else:
            raw = x / n
            z = n / (n + k)  # k = inf -> Z = 0.0 natively
            rate = z * raw + (1.0 - z) * m
        estimates[ctx] = CredibilityEstimate(
            context=ctx, rate=rate, Z=z, n=n, failures=x, raw_rate=raw,
            k=k, collective_mean=m,
        )
    return estimates
