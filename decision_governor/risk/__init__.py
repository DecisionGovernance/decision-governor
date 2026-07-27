"""Risk interface: costs in domain units, CVaR verdicts, credibility.

See docs/risk-worked-example.md — every number there is reproduced
exactly by tests/test_risk.py, so these docs cannot drift from this code.
"""
from decision_governor.risk.costs import CostStructure
from decision_governor.risk.credibility import CredibilityEstimate, buhlmann_straub
from decision_governor.risk.cvar import (
    CVaRPolicy,
    UnmappedCheck,
    bernoulli_cvar,
    discrete_cvar,
    expected_loss,
)

__all__ = [
    "CVaRPolicy",
    "CostStructure",
    "CredibilityEstimate",
    "UnmappedCheck",
    "bernoulli_cvar",
    "buhlmann_straub",
    "discrete_cvar",
    "expected_loss",
]
