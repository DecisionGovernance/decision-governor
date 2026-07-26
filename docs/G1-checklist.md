# Card G-1 — execution record

Steps executed in order:
1. Severity ordering (ALLOW < SCALE < ABSTAIN) and the private worst-of
   helper with an explicit default — the asymmetric defaults in step 6
   are the tighten-only rule.
2. Policy protocol (judge one check result; the engine owns composition)
   plus ThresholdPolicy(scale_at=0.25, abstain_at=0.60) as the
   hand-checkable, zero-dependency reference; bounds validated with the
   actual values in the error.
3. Typed exceptions under GovernorError: NoChecksRegistered,
   UnknownCheck (lists the registered names), InvalidPolicy (names the
   missing protocol method). Every message says what to do.
4. Frozen result shapes: CheckRecord, Verdict (UUID record_id already,
   pre-G-4; derived reasons property renders non-ALLOW checks with
   evidence), GateResult (output + verdict with decision/reasons/
   scale_path conveniences).
5. Governor: policy validated at construction, log accepted and held
   unused (G-4 seam), sorted-name check selection, scale_path attached
   only on SCALE verdicts.
6. _compose: base = worst of deterministic (default SCALE — absence of
   proof is not permission; no deterministic evidence means ALLOW is
   unreachable); escalation = worst of non-deterministic (default
   ALLOW — their absence escalates nothing); verdict = worst of both.
   A learned component can constrain, never authorize.
7. @gate decorator as thin sugar over evaluate(), with the facts kwarg
   extractor (the G-3 ground-truth seam).
8. Acceptance gate: tests/test_engine.py — four Hypothesis property
   tests at 200 examples each (determinism, order-invariance,
   tighten-only, ALLOW-requires-deterministic-evidence) plus example
   tests (quickstart end-to-end, scale_path only on SCALE, actionable
   error text, ceiling-SCALE with learned-only checks, named selection
   and gate context plumbing, UUID record_id).

Review finding addressed (July 25, 2026): evaluate() had checks third,
breaking the frozen positional API evaluate(output, context, scale_path)
— a positional scale_path was consumed as a check sequence. Fixed:
scale_path restored as third parameter, checks made keyword-only, and a
positional-compatibility regression test added.

Gate result (July 25, 2026): 16 tests passed, coverage 100% on
decision_governor/, ruff clean, mypy strict on core/ clean. Card G-1
complete; G-2 (CVaRPolicy) can swap in behind the Policy protocol
without engine changes.
