# Changelog

## [Unreleased]
### Added
- G-1: core engine — Governor with check registry and evaluate(), tighten-only
  decision composition (deterministic base, learned checks escalate only,
  ceiling SCALE without deterministic evidence), Policy protocol with
  ThresholdPolicy reference, frozen CheckRecord/Verdict/GateResult shapes,
  typed GovernorError exceptions, @gate decorator; property-tested for
  determinism, order-invariance, and tighten-only under randomized checks.
- G-0: package scaffold, frozen public contracts (Decision, CheckResult, Check),
  CI matrix (3.10-3.12: ruff, mypy-strict on core/risk, pytest), visible v0.2
  stub for ruin-theory surplus tracking.
