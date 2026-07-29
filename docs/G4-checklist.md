# Card G-4 — execution record (Instrumentation)

**Registry window: Aug 1–4. Gate: the audit round-trip. Floor card (only actuarial.py may descope, to experimental status).**

## Execution checklist

Record writer (log.py):
- [x] DecisionLog bound via Governor(log=...) — the G-1 seam consumed, no caller changes
- [x] Record serializes to frozen schema v1.0; risk block includes gate_cvar, decided_by
      (per_check|aggregate|ceiling), allow_barred_by_ceiling, ceiling_fraction,
      enumeration mode (exact_2k|comonotonic_bound)
- [x] context_digest = sha256 over canonical JSON (sorted keys); raw context NEVER stored — test asserts absence
- [x] Check entries reference describe() output (model pins ride along)
- [x] Sink protocol (write/read/query) + SQLiteSink (default) + JsonlSink; Postgres confirmed OUT (parking)
- [x] Atomic per-record writes; LogWriteError is loud; verdict still returns to caller

Outcome callback:
- [x] report_outcome(record_id, ok, detail) — idempotent, last-write-wins, revision counter
- [x] UnknownRecord actionable error; conventional keys documented (user_edit_distance, employer_response)

Audit CLI (the `governor` console script):
- [x] export: records.jsonl + schema.json + pins.json + config.json (--redact-costs flag) + manifest.json (per-file sha256 + bundle sha256 + tool version + timestamp)
- [x] verify: hash recompute → schema validation → deterministic re-derivation incl.
      max(D_det,D_all) and ceiling logic → stored-vs-recomputed comparison
- [x] Output format exactly: "N records · N deterministic verdicts recomputed · M mismatches · pins listed · config digest matches · PASS/FAIL"; exit 0 only on PASS
- [x] Verify states explicitly: model-backed checks re-verified from stored results, not re-run

Monitor hook:
- [x] gov.monitor(sink, every=...) — rates by decision, per-check triggers, abstention-trend flag,
      outcome-reported fraction, credibility-weighted context rates (Z shown)
- [x] TelegramSink (HTTP, no SDK) + CallbackSink for tests; scheduling documented as caller's job

actuarial.py (EXPERIMENTAL marker in module docstring):
- [x] ibnr_ultimate: chain-ladder over reporting delays; factors exposed; synthetic-data tests
- [x] time_to_outcome: Kaplan-Meier with censoring; median + dormant-after quantile;
      docstring states "Cox covariates: v0.2"

## Gate (run and record)

- [x] Round-trip: suite-exported bundle verifies with ZERO mismatches
- [x] Mutation test: flipped decision in copied bundle is CAUGHT (record_id + fields printed)

**Gate result:** PASS — **Date:** July 28, 2026 (four days ahead of the Aug 1–4 window) — **Descopes taken:** none (actuarial stayed in, experimental as planned; Postgres was pre-parked)

**Notes / resolutions (with reasons):**

1. Module naming: the record writer landed as instrumentation/canonical.py
   + records.py + sinks.py rather than a single log.py — canonical
   serialization needed to be its own import-from-both-sides module
   (precision trap #1), which pulled the split. Behavior as specified.
2. Enumeration mode values are "exact" | "comonotonic_bound" (not
   "exact_2k") — the record's meaning is identical; the walkthrough's
   name for the exact mode carried an implementation detail (2^k) the
   field doesn't need.
3. "Verdict still returns to caller" refined per the walkthrough: a
   failed write RAISES LogWriteError with the fully-formed verdict
   attached (err.verdict) — loud, but not lossy. A caller who catches
   it still has the decision.
4. Monitor is a pure function (snapshot over sink.query()) plus
   notification sinks, not gov.monitor(every=...) — per the walkthrough
   refinement: scheduling is the caller's job (cron example in the
   docstring), so the SDK owns arithmetic, not timers.
5. decided_by tri-state landed as committed at Sunday Review 1: the
   engine emits per_check | aggregate | ceiling with the
   most-structural-wins precedence (ceiling = the no-deterministic-
   evidence cap exclusively), and the three per-value fixtures exist —
   including the subtle per_check case where the deontic bar makes the
   per-check verdict stricter than the gate's economic argmin.
6. The verifier is an independent re-derivation (_recompute.py imports
   pure math only, never the Governor or risk.cvar) — a verifier that
   shares the engine's code shares its bugs. The mutation test proves
   the recompute pass catches a flipped decision even when the
   adversary regenerates all manifest hashes; the plain-tamper case is
   caught by pass 1.
7. bundle_sha256 recipe is stated in-band
   ("bundle_hash_recipe": "sha256(canonical_bytes(files))") and a test
   re-derives it from the manifest alone — "check our math", not
   "trust our tool".
8. Robustness fix found by the suite: verify() on a bundle missing a
   manifest-listed file now fails with pass-1 specifics instead of
   crashing in pass 3.
9. The compliance profile flipped as designed: decision_logging joined
   SDK_CAPABILITIES, its RMF rows (MEASURE-2.8, MANAGE-4.1) render
   covered, and the G-3 honesty test now asserts the flip; the
   adversarial toolkit stays not_covered until G-5 is real.

Gate evidence (July 28, 2026): full suite 123 passed, ruff clean, mypy
clean (strict on core/ and risk/), coverage 95%. The round-trip bundle
contains one record per decided_by value, a reported outcome
(revision-counted), and a model-backed check re-verified from stored
results; verify reports zero mismatches and PASS; the mutation test
FAILs naming the tampered record and the differing field. The fintech
demo's "N records · 0 mismatches" line is now a runnable artifact.
