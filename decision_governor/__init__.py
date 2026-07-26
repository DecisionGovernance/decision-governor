"""Decision Governor: allow / scale / abstain governance for AI outputs and actions."""
from decision_governor.core.engine import Governor, gate
from decision_governor.core.errors import (
    GovernorError,
    InvalidPolicy,
    NoChecksRegistered,
    UnknownCheck,
)
from decision_governor.core.policy import Policy, ThresholdPolicy
from decision_governor.core.results import CheckRecord, GateResult, Verdict
from decision_governor.core.types import Check, CheckResult, Decision, Evidence

__version__ = "0.1.0.dev0"
__all__ = [
    "Check",
    "CheckRecord",
    "CheckResult",
    "Decision",
    "Evidence",
    "GateResult",
    "Governor",
    "GovernorError",
    "InvalidPolicy",
    "NoChecksRegistered",
    "Policy",
    "ThresholdPolicy",
    "UnknownCheck",
    "Verdict",
    "__version__",
    "gate",
]
