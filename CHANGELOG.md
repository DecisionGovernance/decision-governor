# Changelog

## [Unreleased]
### Added
- G-2: risk interface — CostStructure (named costs in domain units, mandatory
  abstention cost), CVaRPolicy (verdict as cost minimization, per-check
  Bernoulli CVaR with closed-form tail, hard ceiling on ALLOW, safer tie-break,
  and a gate-level judge_gate pricing the aggregate tail across all selected
  checks — exact joint enumeration to 12 checks, subadditive comonotonic bound
  beyond — composed tighten-only by the engine),
  Bühlmann–Straub credibility with factors shipped in the output, dynamic
  tighten-biased threshold adjustment via rate_provider; the worked example in
  docs/risk-worked-example.md is parsed by the test suite so docs and code
  cannot drift.
- G-1: core engine — Governor with check registry and evaluate(), tighten-only
  decision composition (deterministic base, learned checks escalate only,
  ceiling SCALE without deterministic evidence), Policy protocol with
  ThresholdPolicy reference, frozen CheckRecord/Verdict/GateResult shapes,
  typed GovernorError exceptions, @gate decorator; property-tested for
  determinism, order-invariance, and tighten-only under randomized checks.
- G-0: package scaffold, frozen public contracts (Decision, CheckResult, Check),
  CI matrix (3.10-3.12: ruff, mypy-strict on core/risk, pytest), visible v0.2
  stub for ruin-theory surplus tracking.
