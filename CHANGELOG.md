# Changelog

## [0.1.0] - 2026-08-08
### Added
- G-4: instrumentation — canonical serialization (single hashed-bytes function,
  NaN/Inf forbidden), schema-v1.0 decision records with context digests (raw
  context never stored), Sink protocol with SQLite (WAL) and JSONL sinks wired
  into Governor(log=...), loud-but-not-lossy LogWriteError carrying the verdict,
  idempotent outcome callback with revision counter, audit export (manifest with
  in-band bundle-hash recipe) and four-pass verify with independent recompute
  (pure-math re-derivation, never the engine), decided_by tri-state
  (per_check|aggregate|ceiling) emitted by the engine, `governor audit
  export|verify` CLI, monitor snapshot with credibility-weighted gate rates,
  and EXPERIMENTAL actuarial methods (chain-ladder IBNR, Kaplan-Meier
  time-to-outcome; Cox covariates deferred to v0.2 per Amendment 2).
- **G-5: adversarial toolkit** — prompt-injection corpus (`corpus_v1.jsonl`) with a catalogued payload set, perturbation/shift harness (rule-based, so testing the system adds no unpinned dependency to it), Clayton-copula cascade stress-testing the gate's independence assumption under lower-tail dependence, and the confident-but-wrong calibration statistic wired for CI (`--fail-on "cbw>0.02"`); misses logged by identifier, and `0 reported outcomes → undefined, not zero` enforced by fixture.
- G-3: check library — deterministic safety/fairness checks (pii_leak with
  masked evidence, output_domain, protected_attribute_leak), hash-pinned model
  infrastructure with frozen digests, model-backed checks with injectable
  backends (style_drift, claims_supported), verdict_disparity monitor,
  compliance checklist runner and NIST AI RMF profile with honest not_covered
  rows (decision_logging flipped to covered when G-4 landed).
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
