"""Card G-5 — the adversarial toolkit: the system attacks itself and
writes down what it learns.

Five components sharing one report artifact (AdversarialReport):
  injection   — replay an attack corpus through the gate
  shift       — rule-based perturbation robustness (loosening flips = CRITICAL)
  cascade     — Clayton copula stress on the independence assumption (protected)
  calibration — confident-but-wrong over the decision log (protected)
and a CI action (`python -m decision_governor.adversarial`) that gates a
build on the reports' whitelisted metrics.
"""
from decision_governor.adversarial import calibration, cascade, injection, shift
from decision_governor.adversarial.calibration import EMPTY_CASE, confident_but_wrong
from decision_governor.adversarial.report import TOOLS, AdversarialReport

__all__ = [
    "EMPTY_CASE",
    "TOOLS",
    "AdversarialReport",
    "calibration",
    "cascade",
    "confident_but_wrong",
    "injection",
    "shift",
]
