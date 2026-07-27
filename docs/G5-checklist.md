# Card G-5 — execution record (Adversarial toolkit)

**Registry window: Aug 2–6. Gate: toolkit runs against the bundled example gate and emits the documented report artifact. Internal descope order: shift first, injection second; cascade + calibration PROTECTED.**

## Execution checklist

injection.py:
- [ ] corpus_v1.jsonl authored (~40–60 entries; categories: instruction override, role-play coercion,
      retrieved-content injection, encoding tricks, tool redirection; fields: id/category/payload/expected_catch)
- [ ] Corpus ships as package data (MANIFEST check in tests)
- [ ] run(target, corpus) → InjectionReport: pass rate overall + by category, misses listed by id
- [ ] Docstring states: tests the GATE's resilience, not the LLM's

shift.py:
- [ ] Rule-based paraphrase (shipped lexicon + clause reorder) — NO model-based perturbation (scope guard)
- [ ] truncate / encoding_noise / vocab_swap harnesses; score deltas + verdict flips measured
- [ ] ABSTAIN→ALLOW under perturbation flagged CRITICAL in report

cascade.py:
- [ ] Clayton sampling with lower-tail dependence; seed parameter MANDATORY, no default; seed in report
- [ ] theta: fit via Kendall's tau inversion when log has ≥N records (N documented), else conservative default
- [ ] Report: independence-priced CVaR vs dependence-simulated CVaR; under-call fraction;
      one-line judgment "independence assumption adequate/strained/unsafe at theta=X"
- [ ] Deterministic under seed (test: two runs, same seed, identical report)

calibration.py:
- [ ] confident_but_wrong(log, floor): ALLOW ∧ all confidences ≥ floor ∧ outcome bad
- [ ] Reliability table (binned confidence vs observed bad-rate) + per-check CBW attribution
- [ ] Empty case wording is a FIXTURE: "0 reported outcomes — statistic undefined, not zero"

CI action:
- [ ] python -m decision_governor.adversarial --target ... --fail-on "<expr>" (whitelisted fields, NO eval())
- [ ] action.yml wrapper; nonzero exit prints the breached clause

## Gate (run and record)

- [ ] Full toolkit runs against the bundled example gate; report artifact matches the docs' shown output

**Gate result:** ____ — **Date:** ____ — **Descopes taken (order honored):** ____
**Notes / resolutions:**
