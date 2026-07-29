"""CVaRPolicy: the verdict as a cost minimization with a tail ceiling."""
from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Any

from decision_governor.core.errors import GovernorError
from decision_governor.core.results import CheckRecord
from decision_governor.core.types import CheckResult, Decision
from decision_governor.risk.costs import CostStructure
from decision_governor.risk.credibility import CredibilityEstimate

_SEVERITY = {Decision.ALLOW: 0, Decision.SCALE: 1, Decision.ABSTAIN: 2}

RateProvider = Callable[[Mapping[str, Any]], "CredibilityEstimate | None"]


class UnmappedCheck(GovernorError):
    def __init__(self, check_name: str, mapped: tuple[str, ...]) -> None:
        listing = ", ".join(repr(n) for n in mapped) if mapped else "(none)"
        super().__init__(
            f"check {check_name!r} has no entry in cost_map (mapped checks: "
            f"{listing}) and no default_cost is set. Add "
            f"cost_map[{check_name!r}] = <cost name>, or pass "
            "default_cost=<cost name> explicitly — silent defaults hide "
            "misconfiguration."
        )
        self.check_name = check_name


def expected_loss(result: CheckResult, cost: float) -> float:
    """score x confidence x cost: the expected loss contribution if the
    action executes. Score is violation likelihood, confidence weights
    how much the estimate is worth, cost converts to domain units."""
    return result.score * result.confidence * cost


def bernoulli_cvar(p: float, cost: float, alpha: float) -> float:
    """CVaR at level alpha of a Bernoulli loss: `cost` with probability p.

    Closed form: the tail is pure loss once p >= alpha, else the tail is
    (p / alpha) occupied. Read out loud: with alpha = 0.05, a check
    reporting even 5% violation probability makes the worst-5%-of-outcomes
    *entirely* loss — CVaR refuses to be comforted by the 95%.

    v0.1 computes per-check Bernoulli CVaR; joint-distribution CVaR across
    correlated checks is exactly what the G-5 Clayton cascade stress-tests,
    and richer loss models are the ruin-theory stub's territory.
    """
    if p >= alpha:
        return cost
    return (p / alpha) * cost


def discrete_cvar(distribution: Mapping[float, float], alpha: float) -> float:
    """CVaR at level alpha of a discrete loss distribution {loss: prob}:
    the mean of the worst alpha-mass of outcomes, with the boundary atom
    taken fractionally."""
    remaining = alpha
    acc = 0.0
    for loss, prob in sorted(distribution.items(), reverse=True):
        take = min(prob, remaining)
        acc += take * loss
        remaining -= take
        if remaining <= 0.0:
            break
    return acc / alpha


class CVaRPolicy:
    """Choose the verdict that minimizes cost in domain units, with the
    CVaR bound as a hard ceiling on ALLOW.

    scale_mitigation: how much of the error cost a constrained execution
    retains — default 0.3, meaning SCALE is assumed to catch ~70% of harm
    via the human-review or reduced-permission path.
    scale_friction: fraction of the abstention cost incurred as friction
    by routing through a scale path.

    ceiling_fraction: the CVaR bound as a hard ceiling on ALLOW. This is
    a *deontic* bar, distinct from the *economic* argmin below it: some
    tail exposures are impermissible regardless of price, and only the
    permitted verdicts get priced. ALLOW is barred when tail loss exceeds
    ceiling_fraction x the full error cost. For p < alpha, this is
    p > alpha x ceiling_fraction; with the default 0.5 ceiling, it is
    p > alpha/2 (2.5% at alpha = 0.05). At p >= alpha, the Bernoulli
    tail is the full error cost and therefore exceeds any ceiling below
    1.0. The ceiling is a fraction of the error cost, not an absolute
    number, so it scales with stakes automatically — re-denominating
    costs never requires re-tuning it. Because ceiling and cost scale
    together, raising a cost raises both the tail loss and the bar
    proportionally, so the "raising any cost never moves a verdict toward
    ALLOW" property stays provable rather than accidentally true. The
    risk block records which kind of "no" fired via allow_barred_by_ceiling.

    Ties break toward the SAFER verdict — a policy indifferent between
    ALLOW and SCALE must SCALE; that is CVaR's asymmetry expressed at the
    boundary.

    judge() prices one check; judge_gate() prices the gate. Per-check
    judging alone cannot see aggregate exposure (two checks each cheap
    enough to ALLOW can jointly carry a tail worth constraining), so the
    engine also calls judge_gate(records, context), which computes the
    combined loss distribution across all selected checks and returns the
    economic argmin over the gate-level candidates. The deontic ceiling
    stays per-check on purpose: in probability space the per-check bar is
    cost-free (p > alpha x ceiling_fraction), so adding a clean check can
    never dilute total exposure into un-barring ALLOW — and the engine's
    composition carries any per-check bar to the gate verdict, while
    composing the aggregate opinion tighten-only.

    rate_provider (dynamic thresholds, bounded): when present, the
    context's credibility-weighted failure rate scales the effective
    violation probability before the CVaR computation. Adjustments are
    tighten-biased: an unusually *good* track record relaxes at most back
    to the unadjusted baseline, never below it. The adjustment factor is
    written into context["risk"] (when the context mapping is mutable, as
    the engine's is) so no verdict is influenced by an invisible number.
    """

    # Exact enumeration is $2^k$ in active checks. Beyond this limit, use
    # the conservative comonotonic upper bound rather than an approximation
    # that could under-price the tail (see _aggregate_tail).
    AGGREGATE_EXACT_LIMIT = 12

    def __init__(
        self,
        alpha: float = 0.05,
        costs: CostStructure | None = None,
        cost_map: Mapping[str, str] | None = None,
        default_cost: str | None = None,
        scale_mitigation: float = 0.3,
        scale_friction: float = 0.5,
        ceiling_fraction: float = 0.5,
        rate_provider: RateProvider | None = None,
    ) -> None:
        if costs is None:
            raise ValueError(
                "CVaRPolicy requires costs: pass a CostStructure with your "
                "error costs and the mandatory abstention cost."
            )
        if not 0.0 < alpha <= 1.0:
            raise ValueError(f"alpha must be in (0, 1], got {alpha}")
        if not 0.0 <= scale_mitigation <= 1.0:
            raise ValueError(f"scale_mitigation must be in [0, 1], got {scale_mitigation}")
        if scale_friction < 0.0:
            raise ValueError(f"scale_friction must be >= 0, got {scale_friction}")
        if not 0.0 < ceiling_fraction <= 1.0:
            raise ValueError(f"ceiling_fraction must be in (0, 1], got {ceiling_fraction}")
        self.alpha = alpha
        self.costs = costs
        self.cost_map = dict(cost_map) if cost_map else {}
        for check_name, cost_name in self.cost_map.items():
            if cost_name not in costs:
                raise ValueError(
                    f"cost_map[{check_name!r}] = {cost_name!r}, but the "
                    f"CostStructure defines only: {', '.join(costs.names)}."
                )
        if default_cost is not None and default_cost not in costs:
            raise ValueError(
                f"default_cost = {default_cost!r} is not in the CostStructure "
                f"(defined: {', '.join(costs.names)})."
            )
        self.default_cost = default_cost
        self.scale_mitigation = scale_mitigation
        self.scale_friction = scale_friction
        self.ceiling_fraction = ceiling_fraction
        self.rate_provider = rate_provider

    def _cost_for(self, check_name: str) -> float:
        cost_name = self.cost_map.get(check_name, self.default_cost)
        if cost_name is None:
            raise UnmappedCheck(check_name, tuple(sorted(self.cost_map)))
        return self.costs.get(cost_name)

    def _adjustment_factor(self, context: Mapping[str, Any]) -> float:
        if self.rate_provider is None:
            return 1.0
        estimate = self.rate_provider(context)
        if estimate is None or estimate.collective_mean <= 0.0:
            return 1.0
        # Tighten-biased: never below the unadjusted baseline.
        return max(1.0, estimate.rate / estimate.collective_mean)

    def judge(
        self, check_name: str, result: CheckResult, context: Mapping[str, Any]
    ) -> Decision:
        c_err = self._cost_for(check_name)
        p_raw = result.score * result.confidence
        factor = self._adjustment_factor(context)
        p = min(1.0, p_raw * factor)

        cost_allow = bernoulli_cvar(p, c_err, self.alpha)
        cost_scale = (
            self.scale_mitigation * cost_allow
            + self.costs.abstention * self.scale_friction
        )
        cost_abstain = self.costs.abstention
        allow_barred = cost_allow > self.ceiling_fraction * c_err

        candidates: dict[Decision, float] = {
            Decision.SCALE: cost_scale,
            Decision.ABSTAIN: cost_abstain,
        }
        if not allow_barred:
            candidates[Decision.ALLOW] = cost_allow

        # argmin; ties break toward the safer (higher-severity) verdict.
        decision = min(
            candidates.items(), key=lambda kv: (kv[1], -_SEVERITY[kv[0]])
        )[0]

        if isinstance(context, MutableMapping):
            risk_block: dict[str, Any] = context.setdefault("risk", {})
            risk_block[check_name] = {
                "alpha": self.alpha,
                "error_cost": c_err,
                "p_raw": p_raw,
                "adjustment_factor": factor,
                "p_effective": p,
                "cvar_allow": cost_allow,
                "cost_scale": cost_scale,
                "cost_abstain": cost_abstain,
                "allow_barred_by_ceiling": allow_barred,
                "verdict": decision.value,
            }
        return decision

    def _aggregate_tail(self, items: Sequence[tuple[float, float]]) -> tuple[float, bool]:
        """(aggregate CVaR, exact?) over independent per-check Bernoulli
        losses [(p, cost), ...].

        Up to AGGREGATE_EXACT_LIMIT active checks, the joint loss
        distribution is enumerated exactly (independence assumed — the
        G-5 Clayton cascade stress-tests exactly that assumption). Beyond
        it, the comonotonic bound sum-of-individual-CVaRs is used: CVaR
        is subadditive, so the bound is conservative under *any*
        dependence structure — the fallback tightens, never loosens.
        """
        active = [(p, c) for p, c in items if p > 0.0]
        if len(active) > self.AGGREGATE_EXACT_LIMIT:
            return sum(bernoulli_cvar(p, c, self.alpha) for p, c in active), False
        if len(active) == 1:
            p, cost = active[0]
            # Preserve exact implementation-level continuity with judge().
            return bernoulli_cvar(p, cost, self.alpha), True
        dist: dict[float, float] = {0.0: 1.0}
        for p, c in active:
            folded: dict[float, float] = {}
            for loss, prob in dist.items():
                folded[loss] = folded.get(loss, 0.0) + prob * (1.0 - p)
                folded[loss + c] = folded.get(loss + c, 0.0) + prob * p
            dist = folded
        return discrete_cvar(dist, self.alpha), True

    def judge_gate(
        self, records: Sequence[CheckRecord], context: Mapping[str, Any]
    ) -> Decision:
        """One gate-level verdict from the combined exposure of all
        selected checks: the economic argmin over aggregate candidates.
        Purely economic by design — the deontic ceiling is enforced
        per-check in judge() and carried to the gate by the engine's
        composition, which also guarantees this opinion only escalates.
        """
        factor = self._adjustment_factor(context)
        items: list[tuple[float, float]] = []
        for record in records:
            c_err = self._cost_for(record.name)
            p = min(1.0, record.result.score * record.result.confidence * factor)
            items.append((p, c_err))

        cvar_gate, exact = self._aggregate_tail(items)
        cost_scale = (
            self.scale_mitigation * cvar_gate
            + self.costs.abstention * self.scale_friction
        )
        cost_abstain = self.costs.abstention
        candidates: dict[Decision, float] = {
            Decision.ALLOW: cvar_gate,
            Decision.SCALE: cost_scale,
            Decision.ABSTAIN: cost_abstain,
        }
        decision = min(
            candidates.items(), key=lambda kv: (kv[1], -_SEVERITY[kv[0]])
        )[0]

        if isinstance(context, MutableMapping):
            risk_block: dict[str, Any] = context.setdefault("risk", {})
            risk_block["__gate__"] = {
                "alpha": self.alpha,
                "adjustment_factor": factor,
                "gate_cvar": cvar_gate,
                "cvar_gate": cvar_gate,  # compatibility alias for v0.1 G-2 callers
                "exact": exact,
                "checks": len(records),
                "assumption": "independent" if exact else "comonotonic upper bound",
                "cost_scale": cost_scale,
                "cost_abstain": cost_abstain,
                "verdict": decision.value,
            }
        return decision
