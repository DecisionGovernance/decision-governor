"""EXPERIMENTAL actuarial methods over decision-log outcomes.

Both functions are labeled experimental: they run on synthetic fixtures
in v0.1 and are exercised against hand-computed values, but no
production claim rests on them. Factors and intermediate quantities are
exposed, never hidden — same discipline as the credibility module.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class IBNREstimate:
    """Chain-ladder over a reporting-delay triangle: outcomes take time
    to arrive, so recent cohorts' counts are incomplete — 'incurred but
    not reported', denominated in outcomes instead of claims."""

    development_factors: tuple[float, ...]   # f_j, exposed for the auditor
    latest_diagonal: tuple[float, ...]
    ultimates: tuple[float, ...]             # projected final counts
    ibnr: tuple[float, ...]                  # ultimate - latest known


def ibnr_ultimate(triangle: Sequence[Sequence[float]]) -> IBNREstimate:
    """Standard chain-ladder on a cumulative reporting triangle.

    triangle[i] is cohort i's cumulative outcome counts by development
    age; later cohorts have fewer known ages. Development factor f_j is
    the volume-weighted ratio between ages j and j+1 over every cohort
    that has both.
    """
    if not triangle or not triangle[0]:
        raise ValueError("ibnr_ultimate needs a non-empty cumulative triangle.")
    ages = len(triangle[0])
    factors: list[float] = []
    for j in range(ages - 1):
        numerator = sum(
            row[j + 1] for row in triangle if len(row) > j + 1
        )
        denominator = sum(
            row[j] for row in triangle if len(row) > j + 1
        )
        if denominator <= 0:
            raise ValueError(
                f"development age {j} has no volume to estimate a factor from."
            )
        factors.append(numerator / denominator)

    latest: list[float] = []
    ultimates: list[float] = []
    for row in triangle:
        known = row[-1]
        latest.append(known)
        ultimate = known
        for j in range(len(row) - 1, ages - 1):
            ultimate *= factors[j]
        ultimates.append(ultimate)
    return IBNREstimate(
        development_factors=tuple(factors),
        latest_diagonal=tuple(latest),
        ultimates=tuple(ultimates),
        ibnr=tuple(u - k for u, k in zip(ultimates, latest)),
    )


@dataclass(frozen=True)
class TimeToOutcome:
    """Kaplan-Meier over reporting delays, with censoring for records
    whose outcome has not (yet) been reported.

    Cox covariates: v0.2 (Registry Amendment 2) — covariate modeling
    requires outcome data the pilot has not yet produced; KM is the
    honest estimator at current evidence.
    """

    times: tuple[float, ...]                 # event times, ascending
    survival: tuple[float, ...]              # S(t) after each event time
    median: float | None                     # first t with S(t) <= 0.5
    dormant_after: float | None              # first t with S(t) <= 0.10


def time_to_outcome(
    durations: Sequence[float], reported: Sequence[bool]
) -> TimeToOutcome:
    """durations[i]: days from decision to outcome (or to now, if the
    outcome is unreported — censored, reported[i] = False)."""
    if len(durations) != len(reported):
        raise ValueError("durations and reported must have equal length.")
    if not durations:
        raise ValueError("time_to_outcome needs at least one record.")

    order = sorted(range(len(durations)), key=lambda i: durations[i])
    at_risk = len(durations)
    survival = 1.0
    times: list[float] = []
    curve: list[float] = []
    index = 0
    while index < len(order):
        t = durations[order[index]]
        events = 0
        removed = 0
        while index < len(order) and durations[order[index]] == t:
            if reported[order[index]]:
                events += 1
            removed += 1
            index += 1
        if events:
            survival *= (at_risk - events) / at_risk
            times.append(t)
            curve.append(survival)
        at_risk -= removed

    def first_at_or_below(level: float) -> float | None:
        for t, s in zip(times, curve):
            if s <= level:
                return t
        return None

    return TimeToOutcome(
        times=tuple(times),
        survival=tuple(curve),
        median=first_at_or_below(0.5),
        dormant_after=first_at_or_below(0.10),
    )
