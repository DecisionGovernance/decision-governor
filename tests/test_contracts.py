"""G-0 tests: the frozen contracts behave as frozen."""
import pytest

from decision_governor import Check, CheckResult, Decision


def test_decision_values_match_petition_vocabulary():
    assert Decision.ALLOW.value == "allow"
    assert Decision.SCALE.value == "scale"
    assert Decision.ABSTAIN.value == "abstain"
    assert Decision.ALLOW.allowed and not Decision.ALLOW.scaled
    assert Decision.SCALE.scaled and not Decision.SCALE.allowed


def test_checkresult_bounds_enforced():
    CheckResult(score=0.0, confidence=1.0)          # clean is legal
    with pytest.raises(ValueError):
        CheckResult(score=1.5, confidence=0.5)      # out-of-range score
    with pytest.raises(ValueError):
        CheckResult(score=0.5, confidence=-0.1)     # out-of-range confidence


def test_any_object_satisfying_protocol_is_a_check():
    class Allowlist:
        name = "allowlist"
        deterministic = True
        def run(self, output, context):
            return CheckResult(score=0.0, confidence=1.0, evidence=["ok"])

    assert isinstance(Allowlist(), Check)           # runtime_checkable protocol


def test_ruin_stub_is_visibly_unimplemented():
    from decision_governor.risk.ruin import GovernanceSurplus
    with pytest.raises(NotImplementedError):
        GovernanceSurplus(initial_surplus=1000.0)
