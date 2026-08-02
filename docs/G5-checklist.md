# Card G-5 — execution record (Adversarial toolkit)

**Registry window: Aug 2–6. Gate: toolkit runs against the bundled example gate and emits the documented report artifact. Internal descope order: shift first, injection second; cascade + calibration PROTECTED.**

## Execution checklist

injection.py:
- [x] corpus_v1.jsonl authored (46 entries; categories: instruction override, role-play coercion,
      retrieved-content injection, encoding tricks, tool redirection — plus domain-evasion attacks and
      benign controls; fields: id/category/payload/expected_catch)
- [x] Corpus ships as package data (MANIFEST check in tests)
- [x] run(target, corpus) → AdversarialReport: pass rate overall + by category, misses listed by id
- [x] Docstring states: tests the GATE's resilience, not the LLM's

shift.py:
- [x] Rule-based paraphrase (shipped lexicon + clause reorder) — NO model-based perturbation (scope guard)
- [x] truncate / encoding_noise / vocab_swap harnesses; score deltas + verdict flips measured
- [x] ABSTAIN→ALLOW under perturbation flagged CRITICAL in report

cascade.py:
- [x] Clayton sampling with lower-tail dependence; seed parameter MANDATORY, no default; seed in report
- [x] theta: fit via Kendall's tau inversion when log has ≥N records (N_MIN = 30, documented), else conservative default
- [x] Report: independence-priced CVaR vs dependence-simulated CVaR; under-call fraction;
      one-line judgment "independence assumption adequate/strained/unsafe at theta=X"
- [x] Deterministic under seed (test: two runs, same seed, identical report)

calibration.py:
- [x] confident_but_wrong(log, floor): ALLOW ∧ all confidences ≥ floor ∧ outcome bad
- [x] Reliability table (binned confidence vs observed bad-rate) + per-check CBW attribution
- [x] Empty case wording is a FIXTURE: "0 reported outcomes — statistic undefined, not zero"

CI action:
- [x] python -m decision_governor.adversarial --target ... --fail-on "<expr>" (whitelisted fields, NO eval())
- [x] action.yml wrapper; nonzero exit prints the breached clause

## Gate (run and record)

- [x] Full toolkit runs against the bundled example gate; report artifact matches the docs' shown output
      (see G5-gate-report.md + g5-report-artifact.jsonl; pinned by
      test_gate_artifact_matches_the_docs_shown_output)

**Gate result:** PASS — **Date:** July 29, 2026 (ahead of the Aug 2–6 window) — **Descopes taken (order honored):** none — shift and injection both landed in full; cascade + calibration (PROTECTED) delivered.
**Notes / resolutions:**

1. The example gate (Step 7) is BUNDLED in the package as
   decision_governor.adversarial.example:build_example_gate rather than
   living only in the test file — the documented artifact must be
   reproducible by users (`--target decision_governor.adversarial.example:build_example_gate`),
   and "bundled" means importable, not copy-pasteable.
2. The report type is one shared AdversarialReport for all four tools
   (report.py), not a per-tool InjectionReport — the CI action, the
   docs, and the technical report consume a single shape, and to_json()
   reuses G-4's canonical serializer so reports inherit the audit
   bundle's reproducibility discipline.
3. Review finding (High, fixed): the theta fit's pairwise statistic
   dropped tied pairs from the denominator (Goodman-Kruskal gamma, not
   the tau-a its docstring claimed), so one joint firing among 30 clean
   records read as tau=1.0 → theta≈198. Now a true tie-aware tau-a over
   all n(n-1)/2 pair comparisons; the sparse-log case is pinned by
   test_theta_fit_is_tie_aware_on_sparse_logs. (tau-b would NOT have
   fixed this — identical indicator vectors give tau-b = 1.0 too.)
4. Review finding (Medium, fixed): the CLI's --target loader invoked
   every callable zero-arg, so a bare (output, context) gate — a valid
   public target shape — crashed. _load_target now distinguishes
   factories from two-argument gates by signature binding.
5. Review findings (Medium, fixed): degenerate inputs now fail loudly
   at the API boundary instead of emitting flattering reports —
   calibration rejects bins < 1 and a confidence floor outside [0, 1];
   cascade rejects n_sims < 1 and an empty marginal list (n_sims=0 used
   to report dependence_cvar=0 and "adequate" from zero samples).
6. The documented artifact's calibration/cascade legs run over a static
   three-record log fixture (shown in G5-gate-report.md) rather than a
   live SQLite log — record ids in a live log are not deterministic,
   and the artifact must be byte-stable. The fixture is exactly what
   the example gate logs for the three shown interactions; the live-log
   path is exercised separately in test_full_toolkit_runs_against_the_example_gate.

Gate evidence (July 29, 2026): full suite 163 passed, ruff clean, mypy
clean (strict on core/ and risk/); the CI action runs end-to-end against
the bundled gate (`--target decision_governor.adversarial.example:build_example_gate
--fail-on "injection_pass < 1.0 or critical_flips > 0"` exits 0).
The documented run (seed 1234) yields
injection 46/46 handled correctly with 44/44 attacks caught for the
right reason; shift 0 loosening flips over 160 perturbed trials (40
stricter flips, stability signal); cascade "independence assumption
adequate at theta=2.00" with theta_source=conservative_default on the
thin fixture log; calibration 1 confident-but-wrong ALLOW over 3
reported outcomes. The canonical reports are staged at
docs/g5-report-artifact.jsonl and shown (findings elided, digests
included) in docs/G5-gate-report.md; the pinning test regenerates the
run and compares byte-for-byte.
