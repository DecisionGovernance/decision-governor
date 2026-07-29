"""Independent re-derivation of the decision path from stored data.

Deliberately does NOT import the Governor, the engine, or risk.cvar: a
verifier that shares the engine's code shares its bugs. The formulas
below are reimplemented from the recorded parameters (and from the
technical report's arithmetic) so a mismatch means the bundle and the
math disagree — not that two call sites of the same function agree with
themselves.

Scope: deterministic recomputation only. Model-backed (non-deterministic)
checks are re-verified FROM their stored CheckResults — the models are
not in the bundle, and the verify report says so.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

SEVERITY = {"allow": 0, "scale": 1, "abstain": 2}
_BY_SEVERITY = {0: "allow", 1: "scale", 2: "abstain"}

AGGREGATE_EXACT_LIMIT = 12


def worst(decisions: Sequence[str], default: str) -> str:
    if not decisions:
        return default
    return _BY_SEVERITY[max(SEVERITY[d] for d in decisions)]


def bernoulli_cvar(p: float, cost: float, alpha: float) -> float:
    if p >= alpha:
        return cost
    return (p / alpha) * cost


def discrete_cvar(distribution: Mapping[float, float], alpha: float) -> float:
    remaining = alpha
    acc = 0.0
    for loss, prob in sorted(distribution.items(), reverse=True):
        take = min(prob, remaining)
        acc += take * loss
        remaining -= take
        if remaining <= 0.0:
            break
    return acc / alpha


def aggregate_tail(
    items: Sequence[tuple[float, float]], alpha: float
) -> tuple[float, bool]:
    active = [(p, c) for p, c in items if p > 0.0]
    if len(active) > AGGREGATE_EXACT_LIMIT:
        return sum(bernoulli_cvar(p, c, alpha) for p, c in active), False
    dist: dict[float, float] = {0.0: 1.0}
    for p, c in active:
        folded: dict[float, float] = {}
        for loss, prob in dist.items():
            folded[loss] = folded.get(loss, 0.0) + prob * (1.0 - p)
            folded[loss + c] = folded.get(loss + c, 0.0) + prob * p
        dist = folded
    return discrete_cvar(dist, alpha), True


def _argmin_safer(candidates: Mapping[str, float]) -> str:
    return min(candidates.items(), key=lambda kv: (kv[1], -SEVERITY[kv[0]]))[0]


def judge_threshold(p: float, scale_at: float, abstain_at: float) -> str:
    if p >= abstain_at:
        return "abstain"
    if p >= scale_at:
        return "scale"
    return "allow"


def cost_for(check_name: str, config: Mapping[str, Any]) -> float | None:
    costs = config.get("costs") or {}
    name = (config.get("cost_map") or {}).get(check_name, config.get("default_cost"))
    if name is None:
        return None
    value = costs.get(name)
    return float(value) if value is not None else None


def judge_cvar(
    p: float, c_err: float, config: Mapping[str, Any]
) -> tuple[str, bool]:
    """(decision, allow_barred_by_ceiling) for one check."""
    alpha = float(config["alpha"])
    cvar_allow = bernoulli_cvar(p, c_err, alpha)
    abstention = float(config["costs"]["abstention"])
    cost_scale = (
        float(config["scale_mitigation"]) * cvar_allow
        + abstention * float(config["scale_friction"])
    )
    barred = cvar_allow > float(config["ceiling_fraction"]) * c_err
    candidates = {"scale": cost_scale, "abstain": abstention}
    if not barred:
        candidates["allow"] = cvar_allow
    return _argmin_safer(candidates), barred


def judge_gate_cvar(
    items: Sequence[tuple[float, float]], config: Mapping[str, Any]
) -> tuple[str, float, bool]:
    """(decision, cvar_gate, exact) over the gate's combined exposure."""
    alpha = float(config["alpha"])
    cvar_gate, exact = aggregate_tail(items, alpha)
    abstention = float(config["costs"]["abstention"])
    cost_scale = (
        float(config["scale_mitigation"]) * cvar_gate
        + abstention * float(config["scale_friction"])
    )
    decision = _argmin_safer(
        {"allow": cvar_gate, "scale": cost_scale, "abstain": abstention}
    )
    return decision, cvar_gate, exact


def compose(checks: Sequence[Mapping[str, Any]]) -> str:
    det = [c["decision"] for c in checks if c["deterministic"]]
    nondet = [c["decision"] for c in checks if not c["deterministic"]]
    base = worst(det, default="scale")
    escalation = worst(nondet, default="allow")
    return worst([base, escalation], default=base)


def effective_p(check: Mapping[str, Any]) -> float:
    """score x confidence, times the recorded adjustment factor if any."""
    p = float(check["score"]) * float(check["confidence"])
    risk = check.get("risk") or {}
    factor = float(risk.get("adjustment_factor", 1.0))
    return min(1.0, p * factor)


def recompute_record(
    record: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, Any]:
    """Re-derive per-check decisions, composition, aggregate, and
    decided_by from stored fields + config parameters. Returns the
    re-derived view; cost-dependent parts are None when costs are
    redacted from the config."""
    policy = config.get("policy", "")
    have_costs = bool(config.get("costs")) and all(
        v is not None for v in (config.get("costs") or {}).values()
    )
    checks = record["checks"]

    per_check: dict[str, str] = {}
    barred: list[str] = []
    items_all: list[tuple[float, float]] = []
    items_det: list[tuple[float, float]] = []
    judgeable = True
    for check in checks:
        p = effective_p(check)
        if policy == "ThresholdPolicy":
            per_check[check["name"]] = judge_threshold(
                p, float(config["scale_at"]), float(config["abstain_at"])
            )
        elif policy == "CVaRPolicy" and have_costs:
            c_err = cost_for(check["name"], config)
            if c_err is None:
                judgeable = False
                continue
            decision, is_barred = judge_cvar(p, c_err, config)
            per_check[check["name"]] = decision
            if is_barred:
                barred.append(check["name"])
            items_all.append((p, c_err))
            if check["deterministic"]:
                items_det.append((p, c_err))
        else:
            judgeable = False

    composed_view = [
        {
            "decision": per_check.get(c["name"], c["decision"]),
            "deterministic": c["deterministic"],
        }
        for c in checks
    ]
    composed = compose(composed_view)

    final = composed
    aggregate_binds = False
    gate_cvar: float | None = None
    exact: bool | None = None
    if policy == "CVaRPolicy" and have_costs and judgeable:
        if items_det:
            det_gate, _, _ = judge_gate_cvar(items_det, config)
        else:
            det_gate = "scale"  # no deterministic evidence can support ALLOW
        all_gate, gate_cvar, exact = judge_gate_cvar(items_all, config)
        final = worst([composed, det_gate, all_gate], default=composed)
        aggregate_binds = (
            max(SEVERITY[det_gate], SEVERITY[all_gate]) == SEVERITY[final]
        )

    has_det = any(c["deterministic"] for c in checks)
    if SEVERITY[final] == 0:
        decided_by = "per_check"
    elif not has_det and final == "scale":
        decided_by = "ceiling"
    elif aggregate_binds:
        decided_by = "aggregate"
    else:
        decided_by = "per_check"

    return {
        "per_check": per_check if judgeable or per_check else None,
        "decision": final if (judgeable or policy == "ThresholdPolicy") else None,
        "decided_by": decided_by if (judgeable or policy == "ThresholdPolicy") else None,
        "allow_barred_by_ceiling": sorted(barred),
        "gate_cvar": gate_cvar,
        "enumeration": (
            None if exact is None else ("exact" if exact else "comonotonic_bound")
        ),
        "judgeable": judgeable,
    }
