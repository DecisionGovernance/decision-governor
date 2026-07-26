"""Decision Governor: allow / scale / abstain governance for AI outputs and actions."""
from decision_governor.core.types import Check, CheckResult, Decision, Evidence

__version__ = "0.1.0.dev0"
__all__ = ["Check", "CheckResult", "Decision", "Evidence", "__version__"]

# Governor and gate are exported here when Card G-1 lands:
# from decision_governor.core.engine import Governor, gate
