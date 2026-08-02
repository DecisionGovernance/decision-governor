"""The Clayton cascade — Step 4 of Card G-5 (protected).

Interrogates the risk interface's declared INDEPENDENCE assumption. The
engine prices the gate's aggregate tail assuming per-check failures are
independent (or a comonotonic bound beyond the exact limit). Real checks
are lower-tail dependent — they fail TOGETHER under distribution shift.
This tool simulates that dependence with a Clayton copula (lower-tail
dependence) and reports how much the independence assumption under-prices
the tail.

Two discipline points:
  * The independence leg CALLS the policy's own pricing rather than
    reimplementing it — the question is "what would the real policy have
    said", so here we WANT the shared code (the inverse of the verifier's
    independent-recompute rule).
  * The seed has NO default. Determinism under seed is the contract, so
    a caller must state the seed and it is echoed in the report.
"""
from __future__ import annotations

import random
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from decision_governor.adversarial.report import AdversarialReport
from decision_governor.core.types import Decision
from decision_governor.risk.cvar import CVaRPolicy, discrete_cvar

_SEVERITY = {Decision.ALLOW: 0, Decision.SCALE: 1, Decision.ABSTAIN: 2}

CLAYTON_DEFAULT_THETA = 2.0        # conservative default when the log is too thin to fit
N_MIN = 30                         # min records to fit theta from data (documented)
# CVaR-ratio thresholds for the one-word judgment (documented, in-band).
JUDGMENT_ADEQUATE = 1.15
JUDGMENT_STRAINED = 1.50


def theta_from_tau(tau: float) -> float:
    """Clayton theta from Kendall's tau: tau = theta / (theta + 2)."""
    tau = max(0.0, min(tau, 0.99))     # Clayton models positive dependence only
    return (2.0 * tau) / (1.0 - tau)


def clayton_sample(k: int, theta: float, rng: random.Random) -> list[float]:
    """One draw of k uniforms from a Clayton copula (lower-tail dependent),
    by the Marshall-Olkin frailty construction: a shared Gamma(1/theta)
    frailty couples the marginals, so small values co-occur — failures
    cluster."""
    frailty = rng.gammavariate(1.0 / theta, 1.0)
    return [
        (1.0 + rng.expovariate(1.0) / frailty) ** (-1.0 / theta)
        for _ in range(k)
    ]


def _empirical_cvar(losses: Sequence[float], alpha: float) -> float:
    n = len(losses)
    if n == 0:
        return 0.0
    counts = Counter(losses)
    return discrete_cvar({loss: c / n for loss, c in counts.items()}, alpha)


def _independence_gate(
    policy: CVaRPolicy, marginals: Sequence[tuple[float, float]]
) -> tuple[float, Decision]:
    """Independence-priced gate CVaR and verdict — via the policy's own
    aggregate pricing, not a reimplementation."""
    cvar_indep, _ = policy._aggregate_tail(list(marginals))
    cost_scale = (
        policy.scale_mitigation * cvar_indep
        + policy.costs.abstention * policy.scale_friction
    )
    candidates = {
        Decision.ALLOW: cvar_indep,
        Decision.SCALE: cost_scale,
        Decision.ABSTAIN: policy.costs.abstention,
    }
    verdict = min(candidates.items(), key=lambda kv: (kv[1], -_SEVERITY[kv[0]]))[0]
    return cvar_indep, verdict


def run(
    policy: CVaRPolicy,
    marginals: Sequence[tuple[float, float]],
    *,
    seed: int,
    theta: float = CLAYTON_DEFAULT_THETA,
    theta_source: str = "supplied",
    n_sims: int = 10_000,
) -> AdversarialReport:
    """Stress the gate's independence assumption at dependence strength
    theta over `marginals` = [(violation_prob, cost), ...]."""
    if seed is None:
        raise ValueError("cascade.run requires an explicit seed — determinism is the contract")
    if theta <= 0.0:
        raise ValueError(f"Clayton theta must be > 0, got {theta}")
    if n_sims < 1:
        raise ValueError(f"n_sims must be >= 1, got {n_sims}")
    items = [(float(p), float(c)) for p, c in marginals]
    if not items:
        raise ValueError("cascade.run requires at least one marginal — an empty gate has no tail to stress")

    alpha = policy.alpha
    abstention = policy.costs.abstention
    cvar_indep, indep_verdict = _independence_gate(policy, items)
    permissive = indep_verdict is not Decision.ABSTAIN

    rng = random.Random(seed)
    losses: list[float] = []
    undercalls = 0
    for _ in range(n_sims):
        u = clayton_sample(len(items), theta, rng)
        loss = sum(cost for (p, cost), ui in zip(items, u) if ui < p)
        losses.append(loss)
        if permissive and loss > abstention:
            undercalls += 1

    cvar_dep = _empirical_cvar(losses, alpha)
    ratio = cvar_dep / cvar_indep if cvar_indep > 0.0 else 1.0
    if ratio < JUDGMENT_ADEQUATE:
        word = "adequate"
    elif ratio < JUDGMENT_STRAINED:
        word = "strained"
    else:
        word = "unsafe"

    metrics = {
        "independence_cvar": cvar_indep,
        "dependence_cvar": cvar_dep,
        "cvar_ratio": ratio,
        "undercall_rate": undercalls / n_sims,
    }
    params = {
        "theta": theta,
        "theta_source": theta_source,
        "n_sims": n_sims,
        "alpha": alpha,
        "independence_verdict": indep_verdict.value,
        "judgment_thresholds": {"adequate": JUDGMENT_ADEQUATE, "strained": JUDGMENT_STRAINED},
    }
    judgment = (
        f"independence assumption {word} at theta={theta:.2f} "
        f"(dependence/independence CVaR = {ratio:.2f})"
    )
    return AdversarialReport(
        tool="cascade",
        seed=seed,
        params=params,
        metrics=metrics,
        findings=[],
        judgment=judgment,
    )


def marginals_from_records(
    records: Sequence[Mapping[str, Any]], policy: CVaRPolicy
) -> list[tuple[float, float]]:
    """Mean per-check (violation prob, cost) across a decision log — the
    stress test's marginals when no fixtures are supplied."""
    sums: dict[str, list[float]] = {}
    for record in records:
        for check in record.get("checks", []):
            p = float(check["score"]) * float(check["confidence"])
            sums.setdefault(check["name"], []).append(p)
    out: list[tuple[float, float]] = []
    for name, ps in sorted(sums.items()):
        out.append((sum(ps) / len(ps), policy._cost_for(name)))
    return out


def fit_theta(records: Sequence[Mapping[str, Any]], fire_at: float = 0.5) -> tuple[float, str]:
    """Fit Clayton theta from a log via average pairwise Kendall's tau on
    per-check failure indicators, when there are >= N_MIN records; else
    fall back to the conservative default."""
    if len(records) < N_MIN:
        return CLAYTON_DEFAULT_THETA, "conservative_default"
    names = sorted({c["name"] for r in records for c in r.get("checks", [])})
    if len(names) < 2:
        return CLAYTON_DEFAULT_THETA, "conservative_default"
    vectors = []
    for r in records:
        by_name = {c["name"]: float(c["score"]) * float(c["confidence"]) for c in r.get("checks", [])}
        vectors.append([1 if by_name.get(n, 0.0) >= fire_at else 0 for n in names])
    taus = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            taus.append(_kendall_tau_binary([(v[i], v[j]) for v in vectors]))
    tau = sum(taus) / len(taus) if taus else 0.0
    return theta_from_tau(tau), "kendall_tau_inversion"


def _kendall_tau_binary(pairs: Sequence[tuple[int, int]]) -> float:
    """Kendall's tau-a on binary pairs: concordant minus discordant over
    ALL n*(n-1)/2 pair comparisons. Ties stay in the denominator — sparse
    decision logs are predominantly ties, and dropping tied pairs
    (Goodman-Kruskal gamma) lets a single joint firing among otherwise
    clean records read as tau=1.0 and blow up the Clayton inversion."""
    n = len(pairs)
    if n < 2:
        return 0.0
    counts = Counter(pairs)
    n11, n00 = counts[(1, 1)], counts[(0, 0)]
    n10, n01 = counts[(1, 0)], counts[(0, 1)]
    concordant = n11 * n00
    discordant = n10 * n01
    return (concordant - discordant) / (n * (n - 1) / 2)
