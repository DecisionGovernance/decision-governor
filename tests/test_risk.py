"""G-2 tests: the worked example in docs/risk-worked-example.md is the
fixture. The tables are parsed from the page itself, so if either the
docs or the implementation drifts, this suite fails.

Plus the card's degenerate cases (zero observations, single context,
all-costs-equal ties break safer) and the monotonicity-of-caution
property: raising any error cost never moves the verdict toward ALLOW.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from decision_governor import CheckRecord, CheckResult, Decision, Governor
from decision_governor.risk import (
    CostStructure,
    CVaRPolicy,
    UnmappedCheck,
    bernoulli_cvar,
    buhlmann_straub,
    discrete_cvar,
    expected_loss,
)


class FixedCheck:
    def __init__(self, name, deterministic, score, confidence=1.0):
        self.name = name
        self.deterministic = deterministic
        self._result = CheckResult(score=score, confidence=confidence)

    def run(self, output, context):
        return self._result

SEVERITY = {Decision.ALLOW: 0, Decision.SCALE: 1, Decision.ABSTAIN: 2}
DOC = Path(__file__).resolve().parent.parent / "docs" / "risk-worked-example.md"


def parse_doc_table(marker: str) -> list[dict[str, str]]:
    lines = DOC.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"<!-- table:{marker} -->")
    rows = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("|"):
            rows.append([c.strip() for c in stripped.strip("|").split("|")])
        elif rows:
            break
    header, data = rows[0], rows[2:]  # rows[1] is the separator
    return [dict(zip(header, r)) for r in data]


# ------------------------------------------------- the docs as a fixture


def test_worked_example_verdict_table_reproduces_exactly():
    rows = parse_doc_table("verdicts")
    assert len(rows) == 3
    for row in rows:
        costs = CostStructure(
            unsupported_claim=float(row["cost_err"]),
            abstention=float(row["abstention"]),
        )
        policy = CVaRPolicy(
            alpha=0.05,
            costs=costs,
            cost_map={"claims_supported": "unsupported_claim"},
        )
        result = CheckResult(
            score=float(row["score"]), confidence=float(row["confidence"])
        )
        context: dict = {}
        verdict = policy.judge("claims_supported", result, context)
        risk = context["risk"]["claims_supported"]

        assert round(risk["p_effective"], 6) == float(row["p"])
        assert round(risk["cvar_allow"], 6) == float(row["cvar_allow"])
        assert risk["allow_barred_by_ceiling"] is (row["allow_barred"] == "true")
        assert round(risk["cost_scale"], 6) == float(row["cost_scale"])
        assert round(risk["cost_abstain"], 6) == float(row["cost_abstain"])
        assert verdict.value == row["verdict"]


def test_worked_example_credibility_tables_reproduce_exactly():
    observations = {
        row["context"]: (int(row["n"]), int(row["x"]))
        for row in parse_doc_table("credibility-contexts")
    }
    estimates = buhlmann_straub(observations)

    collective = {r["quantity"]: float(r["value"]) for r in parse_doc_table("credibility-collective")}
    any_est = next(iter(estimates.values()))
    assert round(any_est.collective_mean, 6) == collective["m"]
    assert round(any_est.k, 6) == collective["k"]
    # s2 and a are internal to the estimator; recompute them by hand here
    # exactly as the docs derivation does, from the same observations.
    total_n = sum(n for n, _ in observations.values())
    m = sum(x for _, x in observations.values()) / total_n
    rates = {c: x / n for c, (n, x) in observations.items()}
    s2 = sum(n * rates[c] * (1 - rates[c]) for c, (n, _) in observations.items()) / total_n
    dev = sum(n * (rates[c] - m) ** 2 for c, (n, _) in observations.items())
    denom = total_n - sum(n * n for n, _ in observations.values()) / total_n
    a = (dev - (len(observations) - 1) * s2) / denom
    assert round(s2, 6) == collective["s2"]
    assert round(a, 6) == collective["a"]
    assert round(s2 / a, 6) == collective["k"]

    for row in parse_doc_table("credibility-contexts"):
        est = estimates[row["context"]]
        assert round(est.raw_rate, 6) == float(row["raw_rate"])
        assert round(est.Z, 6) == float(row["Z"])
        assert round(est.rate, 6) == float(row["credibility_rate"])


# ------------------------------------------------------- cost structure


def test_abstention_cost_is_mandatory():
    with pytest.raises(ValueError, match="will always refuse"):
        CostStructure(unsupported_claim=100.0)


def test_costs_must_be_strictly_positive_and_error_names_the_key():
    with pytest.raises(ValueError, match=r"'pii_exposure'.*0"):
        CostStructure(pii_exposure=0.0, abstention=1.0)


def test_cost_structure_exposes_names_get_and_total_exposure():
    costs = CostStructure(unsupported_claim=100.0, pii_exposure=40.0, abstention=3.0)
    assert costs.names == ("abstention", "pii_exposure", "unsupported_claim")
    assert costs.get("pii_exposure") == 40.0
    assert costs.abstention == 3.0
    assert costs.total_exposure == 140.0  # abstention is a choice, not an error
    with pytest.raises(KeyError, match="defined costs"):
        costs.get("typo")
    with pytest.raises(AttributeError, match="frozen"):
        costs.new_field = 1.0
    assert "abstention=3.0" in repr(costs)
    assert dict(costs.as_dict()) == {
        "unsupported_claim": 100.0, "pii_exposure": 40.0, "abstention": 3.0
    }


# ---------------------------------------------------------- cvar policy


def test_unmapped_check_requires_explicit_default_cost():
    costs = CostStructure(unsupported_claim=100.0, abstention=3.0)
    strict = CVaRPolicy(alpha=0.05, costs=costs, cost_map={})
    with pytest.raises(UnmappedCheck, match="default_cost"):
        strict.judge("mystery_check", CheckResult(score=0.5, confidence=1.0), {})

    lenient = CVaRPolicy(
        alpha=0.05, costs=costs, cost_map={}, default_cost="unsupported_claim"
    )
    assert lenient.judge("mystery_check", CheckResult(0.5, 1.0), {}) is Decision.ABSTAIN


def test_policy_construction_validates_loudly():
    costs = CostStructure(err=10.0, abstention=1.0)
    with pytest.raises(ValueError, match="requires costs"):
        CVaRPolicy(alpha=0.05)
    with pytest.raises(ValueError, match="alpha"):
        CVaRPolicy(alpha=0.0, costs=costs)
    with pytest.raises(ValueError, match="scale_mitigation"):
        CVaRPolicy(costs=costs, scale_mitigation=1.5)
    with pytest.raises(ValueError, match="scale_friction"):
        CVaRPolicy(costs=costs, scale_friction=-0.1)
    with pytest.raises(ValueError, match="ceiling_fraction"):
        CVaRPolicy(costs=costs, ceiling_fraction=0.0)
    with pytest.raises(ValueError, match=r"cost_map\['c'\] = 'typo'"):
        CVaRPolicy(costs=costs, cost_map={"c": "typo"})
    with pytest.raises(ValueError, match="default_cost"):
        CVaRPolicy(costs=costs, default_cost="typo")


def test_all_costs_equal_ties_break_toward_the_safer_verdict():
    # Engineered exact-float three-way tie: alpha=0.5, p=0.25 ->
    # cvar = 0.5 * 8 = 4; scale = 0.5*4 + 0.5*4 = 4; abstain = 4.
    costs = CostStructure(err=8.0, abstention=4.0)
    policy = CVaRPolicy(
        alpha=0.5, costs=costs, cost_map={"c": "err"},
        scale_mitigation=0.5, scale_friction=0.5, ceiling_fraction=0.5,
    )
    context: dict = {}
    verdict = policy.judge("c", CheckResult(score=0.25, confidence=1.0), context)
    risk = context["risk"]["c"]
    assert risk["cvar_allow"] == risk["cost_scale"] == risk["cost_abstain"] == 4.0
    assert verdict is Decision.ABSTAIN  # indifference resolves to the safest


def test_bernoulli_cvar_closed_form_and_expected_loss():
    assert bernoulli_cvar(0.0, 100.0, 0.05) == 0.0
    assert bernoulli_cvar(0.05, 100.0, 0.05) == 100.0  # tail entirely loss
    assert bernoulli_cvar(1.0, 100.0, 0.05) == 100.0
    assert round(bernoulli_cvar(0.025, 100.0, 0.05), 6) == 50.0
    # CVaR at alpha = 1 is the plain expected loss.
    result = CheckResult(score=0.3, confidence=0.5)
    assert bernoulli_cvar(0.15, 100.0, 1.0) == expected_loss(result, 100.0)
    # discrete_cvar agrees with the Bernoulli closed form.
    assert discrete_cvar({100.0: 0.05, 0.0: 0.95}, 0.05) == 100.0
    assert round(discrete_cvar({100.0: 0.025, 0.0: 0.975}, 0.05), 6) == 50.0


# ------------------------------------------------ aggregate gate verdict


def _aggregate_governor(n_checks, score=0.001):
    costs = CostStructure(err=100.0, abstention=3.0)
    policy = CVaRPolicy(alpha=0.05, costs=costs, default_cost="err")
    gov = Governor(policy=policy)
    for i in range(n_checks):
        gov.register(FixedCheck(f"check_{i}", True, score))
    return gov


def test_aggregate_gate_verdict_reproduces_docs_and_escalates():
    vals = {r["quantity"]: r["value"] for r in parse_doc_table("aggregate")}
    gov = _aggregate_governor(2, score=float(vals["p_each"]))
    context: dict = {}
    verdict = gov.evaluate("output", context)

    # Each check individually is ALLOW — exactly the gap per-check
    # judging cannot see...
    assert all(r.decision is Decision.ALLOW for r in verdict.records)
    for name in ("check_0", "check_1"):
        assert round(context["risk"][name]["cvar_allow"], 6) == float(vals["cvar_each"])
        assert context["risk"][name]["verdict"] == vals["verdict_each"]

    # ...while the gate's combined tail prices SCALE as cheapest.
    gate = context["risk"]["__gate__"]
    assert gate["exact"] is True
    assert round(gate["cvar_gate"], 6) == float(vals["cvar_gate"])
    assert round(gate["cost_scale"], 6) == float(vals["cost_scale_gate"])
    assert round(gate["cost_abstain"], 6) == float(vals["cost_abstain"])
    assert gate["gate_cvar"] == gate["cvar_gate"]
    assert gate["decided_by"] == "aggregate"
    assert verdict.decision.value == vals["verdict_gate"]
    assert verdict.reasons == [
        "gate tail cost 4.0 vs abstention 3.0 (2 checks, independent)"
    ]


def test_aggregate_beyond_exact_limit_uses_conservative_bound():
    gov = _aggregate_governor(13, score=0.001)  # limit is 12
    context: dict = {}
    verdict = gov.evaluate("output", context)
    gate = context["risk"]["__gate__"]
    assert gate["exact"] is False
    # Comonotonic bound: the sum of the 13 individual CVaRs of 2.0 each.
    assert round(gate["cvar_gate"], 6) == 26.0
    # scale = 0.3 * 26 + 1.5 = 9.3 vs abstain = 3.0 -> ABSTAIN.
    assert verdict.decision is Decision.ABSTAIN


@settings(max_examples=200)
@given(
    specs=st.lists(
        st.tuples(
            st.booleans(),
            st.floats(0.0, 1.0, allow_nan=False),
            st.floats(0.0, 1.0, allow_nan=False),
        ),
        min_size=1,
        max_size=5,
    ),
    extra_deterministic=st.booleans(),
    extra_score=st.floats(0.0, 1.0, allow_nan=False),
    extra_conf=st.floats(0.0, 1.0, allow_nan=False),
)
def test_adding_any_check_never_loosens_a_gate_with_deterministic_evidence(
    specs, extra_deterministic, extra_score, extra_conf
):
    # Once deterministic evidence exists, adding a nonnegative loss cannot
    # lower either the deterministic or all-record aggregate tail. "Any"
    # means any: the added check ranges over deterministic AND learned
    # (the ceiling-lift exception cannot fire — the ceiling is already
    # lifted by the guaranteed deterministic base).
    costs = CostStructure(err=100.0, abstention=3.0)

    def final_decision(all_specs, extra=None):
        policy = CVaRPolicy(alpha=0.05, costs=costs, default_cost="err")
        gov = Governor(policy=policy)
        gov.register(FixedCheck("deterministic_base", True, 0.0))
        for i, (det, score, conf) in enumerate(all_specs):
            gov.register(FixedCheck(f"check_{i}", det, score, conf))
        if extra is not None:
            det, score, conf = extra
            gov.register(FixedCheck("extra", det, score, conf))
        return gov.evaluate("output").decision

    before = final_decision(specs)
    after = final_decision(specs, (extra_deterministic, extra_score, extra_conf))
    assert SEVERITY[after] >= SEVERITY[before]


def test_clean_deterministic_evidence_intentionally_lifts_the_scale_ceiling():
    costs = CostStructure(err=100.0, abstention=3.0)
    policy = CVaRPolicy(alpha=0.05, costs=costs, default_cost="err")
    gov = Governor(policy=policy)
    gov.register(FixedCheck("learned", False, 0.0))
    assert gov.evaluate("output").decision is Decision.SCALE

    gov.register(FixedCheck("deterministic", True, 0.0))
    assert gov.evaluate("output").decision is Decision.ALLOW


@settings(max_examples=200)
@given(
    score=st.floats(0.0, 1.0, allow_nan=False),
    confidence=st.floats(0.0, 1.0, allow_nan=False),
    error_cost=st.floats(0.01, 1000.0, allow_nan=False),
    abstention=st.floats(0.01, 1000.0, allow_nan=False),
)
def test_single_check_gate_tail_reduces_to_per_check_bernoulli_arithmetic(
    score, confidence, error_cost, abstention
):
    policy = CVaRPolicy(
        alpha=0.05,
        costs=CostStructure(err=error_cost, abstention=abstention),
        default_cost="err",
    )
    result = CheckResult(score, confidence)
    per_check_context: dict = {}
    policy.judge("check", result, per_check_context)
    gate_context: dict = {}
    policy.judge_gate(
        [CheckRecord("check", True, result, Decision.ALLOW)], gate_context
    )

    per_check = per_check_context["risk"]["check"]
    gate = gate_context["risk"]["__gate__"]
    assert gate["gate_cvar"] == per_check["cvar_allow"]
    assert gate["cost_scale"] == per_check["cost_scale"]
    assert gate["cost_abstain"] == per_check["cost_abstain"]


def test_cvar_policy_plugs_into_the_g1_engine_unchanged():
    class SingleCheck:
        name = "claims_supported"
        deterministic = True

        def __init__(self, score):
            self._score = score

        def run(self, output, context):
            return CheckResult(score=self._score, confidence=0.9)

    costs = CostStructure(unsupported_claim=100.0, abstention=3.0)
    policy = CVaRPolicy(
        alpha=0.05, costs=costs, cost_map={"claims_supported": "unsupported_claim"}
    )
    gov = Governor(policy=policy)
    gov.register(SingleCheck(score=0.04))
    verdict = gov.evaluate("output", {})
    assert verdict.decision is Decision.ABSTAIN  # docs row 1, end to end


@settings(max_examples=200)
@given(
    score=st.floats(0.0, 1.0, allow_nan=False),
    confidence=st.floats(0.0, 1.0, allow_nan=False),
    c_err=st.floats(0.01, 1000.0, allow_nan=False),
    abstention=st.floats(0.01, 1000.0, allow_nan=False),
    bump=st.floats(0.0, 1000.0, allow_nan=False),
)
def test_raising_an_error_cost_never_moves_the_verdict_toward_allow(
    score, confidence, c_err, abstention, bump
):
    def verdict(err_cost):
        policy = CVaRPolicy(
            alpha=0.05,
            costs=CostStructure(err=err_cost, abstention=abstention),
            cost_map={"c": "err"},
        )
        return policy.judge("c", CheckResult(score, confidence), {})

    before = verdict(c_err)
    after = verdict(c_err + bump)
    assert SEVERITY[after] >= SEVERITY[before]


@settings(max_examples=200)
@given(
    score=st.floats(0.0, 1.0, allow_nan=False),
    confidence=st.floats(0.0, 1.0, allow_nan=False),
    c_err=st.floats(0.01, 1000.0, allow_nan=False),
    abstention=st.floats(0.01, 1000.0, allow_nan=False),
    f1=st.floats(0.001, 1.0, allow_nan=False),
    f2=st.floats(0.001, 1.0, allow_nan=False),
)
def test_lowering_the_ceiling_never_moves_the_verdict_toward_allow(
    score, confidence, c_err, abstention, f1, f2
):
    # The deontic bar only shrinks the candidate set: a stricter ceiling
    # can bar ALLOW but never un-bar it, and never reprices SCALE/ABSTAIN.
    lo, hi = sorted((f1, f2))

    def verdict(fraction):
        policy = CVaRPolicy(
            alpha=0.05,
            costs=CostStructure(err=c_err, abstention=abstention),
            cost_map={"c": "err"},
            ceiling_fraction=fraction,
        )
        return policy.judge("c", CheckResult(score, confidence), {})

    assert SEVERITY[verdict(lo)] >= SEVERITY[verdict(hi)]


# ----------------------------------------------------------- credibility


def test_zero_observation_context_gets_collective_mean_stated_as_such():
    estimates = buhlmann_straub({"a": (50, 5), "b": (50, 10), "new": (0, 0)})
    new = estimates["new"]
    assert new.Z == 0.0
    assert new.raw_rate is None
    assert new.rate == new.collective_mean == 0.15


def test_indistinguishable_contexts_send_everyone_to_the_collective_mean():
    estimates = buhlmann_straub({"a": (50, 5), "b": (50, 5)})
    for est in estimates.values():
        assert math.isinf(est.k)
        assert est.Z == 0.0
        assert est.rate == est.collective_mean == 0.1


def test_all_data_in_one_context_degenerates_to_the_collective_mean():
    # "b" exists but has no trials: between-variance is inestimable
    # (denominator 0), so a floors at 0 and everyone gets the mean.
    estimates = buhlmann_straub({"a": (50, 5), "b": (0, 0)})
    assert math.isinf(estimates["a"].k)
    assert estimates["a"].Z == 0.0
    assert estimates["a"].rate == estimates["b"].rate == 0.1


def test_provider_returning_none_leaves_the_baseline_untouched():
    policy = _policy_with_provider(lambda ctx: None)
    context: dict = {}
    assert policy.judge("c", CheckResult(0.001, 1.0), context) is Decision.ALLOW
    assert context["risk"]["c"]["adjustment_factor"] == 1.0


def test_single_context_returns_raw_rate_flagged_degenerate():
    (est,) = buhlmann_straub({"only": (40, 4)}).values()
    assert est.rate == 0.1
    assert est.Z == 1.0
    assert est.degenerate is True
    assert math.isnan(est.k)  # no between-variance exists to estimate


def test_credibility_input_validation_is_actionable():
    with pytest.raises(ValueError, match="at least one context"):
        buhlmann_straub({})
    with pytest.raises(ValueError, match="failures <= trials"):
        buhlmann_straub({"a": (5, 6)})
    with pytest.raises(ValueError, match="trials > 0"):
        buhlmann_straub({"a": (0, 0)})


# -------------------------------------------- dynamic thresholds (step 6)


def _policy_with_provider(provider):
    costs = CostStructure(err=100.0, abstention=3.0)
    return CVaRPolicy(alpha=0.05, costs=costs, cost_map={"c": "err"}, rate_provider=provider)


def _estimate(rate, collective_mean):
    from decision_governor.risk import CredibilityEstimate

    return CredibilityEstimate(
        context="ctx", rate=rate, Z=0.5, n=10, failures=1,
        raw_rate=rate, k=10.0, collective_mean=collective_mean,
    )


def test_bad_track_record_tightens_and_the_factor_is_visible():
    # Baseline (docs row 3 shape): p = 0.001 -> ALLOW.
    baseline = _policy_with_provider(None)
    assert baseline.judge("c", CheckResult(0.001, 1.0), {}) is Decision.ALLOW

    tightened = _policy_with_provider(lambda ctx: _estimate(rate=0.36, collective_mean=0.12))
    context: dict = {}
    verdict = tightened.judge("c", CheckResult(0.001, 1.0), context)
    risk = context["risk"]["c"]
    assert risk["adjustment_factor"] == 3.0  # never an invisible number
    assert round(risk["p_effective"], 6) == 0.003
    assert verdict is Decision.ABSTAIN  # 3x the track record: escalated


def test_good_track_record_relaxes_at_most_to_baseline():
    relaxed = _policy_with_provider(lambda ctx: _estimate(rate=0.01, collective_mean=0.12))
    context: dict = {}
    verdict = relaxed.judge("c", CheckResult(0.001, 1.0), context)
    assert context["risk"]["c"]["adjustment_factor"] == 1.0  # tighten-biased floor
    assert verdict is Decision.ALLOW  # identical to the unadjusted baseline
