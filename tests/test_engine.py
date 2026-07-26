"""G-1 tests: prove the composition guarantees, don't assert them.

Four properties under randomized check outputs — determinism,
order-invariance, tighten-only, ALLOW-requires-deterministic-evidence —
plus the example tests the card names: the quickstart end-to-end,
scale_path attaching only on SCALE, and the typed errors carrying their
actionable text.
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from decision_governor import (
    CheckResult,
    Decision,
    GateResult,
    Governor,
    GovernorError,
    InvalidPolicy,
    NoChecksRegistered,
    ThresholdPolicy,
    UnknownCheck,
    Verdict,
    gate,
)

SEVERITY = {Decision.ALLOW: 0, Decision.SCALE: 1, Decision.ABSTAIN: 2}


class FixedCheck:
    """Test double: a check that always returns the same result."""

    def __init__(self, name, deterministic, score, confidence=1.0, evidence=()):
        self.name = name
        self.deterministic = deterministic
        self._result = CheckResult(
            score=score, confidence=confidence, evidence=list(evidence)
        )

    def run(self, output, context):
        return self._result


# (deterministic?, score, confidence) triples; names assigned by index.
unit = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
check_specs = st.lists(st.tuples(st.booleans(), unit, unit), min_size=1, max_size=6)


def make_checks(specs):
    return [
        FixedCheck(f"check_{i}", det, score, conf)
        for i, (det, score, conf) in enumerate(specs)
    ]


def governor_from(checks):
    gov = Governor()
    for check in checks:
        gov.register(check)
    return gov


# ---------------------------------------------------------------- properties


@settings(max_examples=200)
@given(specs=check_specs)
def test_determinism_same_inputs_identical_verdict(specs):
    gov = governor_from(make_checks(specs))
    v1 = gov.evaluate("output")
    v2 = gov.evaluate("output")
    assert v1.decision == v2.decision
    assert v1.records == v2.records
    assert v1.reasons == v2.reasons


@settings(max_examples=200)
@given(specs=check_specs, rnd=st.randoms(use_true_random=False))
def test_order_invariance_shuffled_registration_same_verdict(specs, rnd):
    checks = make_checks(specs)
    shuffled = list(checks)
    rnd.shuffle(shuffled)
    v_sorted = governor_from(checks).evaluate("output")
    v_shuffled = governor_from(shuffled).evaluate("output")
    assert v_sorted.decision == v_shuffled.decision
    assert v_sorted.records == v_shuffled.records


@settings(max_examples=200)
@given(specs=check_specs, score=unit, confidence=unit)
def test_tighten_only_adding_nondeterministic_check_never_loosens(specs, score, confidence):
    gov = governor_from(make_checks(specs))
    before = gov.evaluate("output").decision
    gov.register(FixedCheck("zz_learned_judge", False, score, confidence))
    after = gov.evaluate("output").decision
    assert SEVERITY[after] >= SEVERITY[before]


@settings(max_examples=200)
@given(specs=check_specs)
def test_allow_requires_deterministic_evidence(specs):
    nondet_only = [FixedCheck(f"nd_{i}", False, s, c) for i, (_, s, c) in enumerate(specs)]
    verdict = governor_from(nondet_only).evaluate("output")
    assert verdict.decision is not Decision.ALLOW


# ------------------------------------------------------------------ examples


def test_quickstart_end_to_end():
    class NoAbsoluteClaims:
        name = "no_absolute_claims"
        deterministic = True

        def run(self, output, context):
            hit = "guaranteed" in output.lower()
            return CheckResult(score=1.0 if hit else 0.0, confidence=1.0,
                               evidence=[f"'guaranteed' present={hit}"])

    gov = Governor()
    gov.register(NoAbsoluteClaims())

    @gate(gov, scale_path="add_disclaimer")
    def summarize(text: str) -> str:
        return f"Summary: {text}"

    ok = summarize(text="modest returns expected")
    assert isinstance(ok, GateResult)
    assert ok.decision is Decision.ALLOW
    assert ok.output == "Summary: modest returns expected"
    assert ok.reasons == []

    bad = summarize(text="GUARANTEED profit")
    assert bad.decision is Decision.ABSTAIN
    assert bad.scale_path is None  # ABSTAIN, not SCALE: no path attached
    assert any("no_absolute_claims" in line for line in bad.reasons)


def test_scale_path_attaches_only_on_scale():
    def verdict_for(score):
        gov = governor_from([FixedCheck("c", True, score)])
        return gov.evaluate("output", scale_path="human_review")

    allow, scale, abstain = verdict_for(0.0), verdict_for(0.4), verdict_for(1.0)
    assert allow.decision is Decision.ALLOW and allow.scale_path is None
    assert scale.decision is Decision.SCALE and scale.scale_path == "human_review"
    assert abstain.decision is Decision.ABSTAIN and abstain.scale_path is None


def test_typed_errors_carry_actionable_text():
    with pytest.raises(NoChecksRegistered, match=r"gov\.register\(\)"):
        Governor().evaluate("output")

    gov = governor_from([FixedCheck("alpha", True, 0.0), FixedCheck("beta", True, 0.0)])
    with pytest.raises(UnknownCheck, match=r"'alpha', 'beta'"):
        gov.evaluate("output", checks=["alpha", "stray"])

    class NotAPolicy:
        pass

    with pytest.raises(InvalidPolicy, match=r"judge"):
        Governor(policy=NotAPolicy())

    for err in (NoChecksRegistered, UnknownCheck, InvalidPolicy):
        assert issubclass(err, GovernorError)


def test_threshold_policy_validates_and_names_actual_values():
    with pytest.raises(ValueError, match=r"scale_at=0\.9.*abstain_at=0\.2"):
        ThresholdPolicy(scale_at=0.9, abstain_at=0.2)


def test_no_deterministic_evidence_means_ceiling_scale():
    # A perfectly clean learned check still cannot reach ALLOW.
    gov = governor_from([FixedCheck("learned", False, 0.0)])
    assert gov.evaluate("output").decision is Decision.SCALE


def test_named_check_selection_and_context_plumbing():
    seen = {}

    class Recorder:
        name = "recorder"
        deterministic = True

        def run(self, output, context):
            seen.update(context)
            return CheckResult(score=0.0, confidence=1.0)

    gov = governor_from([Recorder(), FixedCheck("hot", True, 1.0)])

    # Named selection: the ABSTAIN-ing check is excluded by name.
    assert gov.evaluate("output", checks=["recorder"]).decision is Decision.ALLOW

    @gate(gov, checks=["recorder"], facts=lambda kwargs: kwargs["source"])
    def answer(question: str, source: str) -> str:
        return "answer"

    result = answer(question="q", source="ground truth")
    assert result.decision is Decision.ALLOW
    assert seen["gate"] == "answer"
    assert seen["facts"] == "ground truth"
    assert seen["kwargs"] == {"question": "q", "source": "ground truth"}


def test_evaluate_positional_scale_path_is_third_parameter():
    # Frozen contract: evaluate(output, context, scale_path). A positional
    # scale_path must never be swallowed by checks (which is keyword-only).
    gov = governor_from([FixedCheck("c", True, 0.4)])
    verdict = gov.evaluate("output", {"caller": "test"}, "human_review")
    assert verdict.decision is Decision.SCALE
    assert verdict.scale_path == "human_review"

    with pytest.raises(TypeError):
        gov.evaluate("output", {}, "human_review", ["c"])  # checks positionally


def test_verdict_record_id_is_uuid_string():
    import uuid

    verdict = governor_from([FixedCheck("c", True, 0.0)]).evaluate("output")
    assert isinstance(verdict, Verdict)
    assert str(uuid.UUID(verdict.record_id)) == verdict.record_id
