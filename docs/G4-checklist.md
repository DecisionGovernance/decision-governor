# Card G-4 — execution record (Instrumentation)

**Registry window: Aug 1–4. Gate: the audit round-trip. Floor card (only actuarial.py may descope, to experimental status).**

## Execution checklist

Record writer (log.py):
- [ ] DecisionLog bound via Governor(log=...) — the G-1 seam consumed, no caller changes
- [ ] Record serializes to frozen schema v1.0; risk block includes gate_cvar, decided_by
      (per_check|aggregate|ceiling), allow_barred_by_ceiling, ceiling_fraction,
      enumeration mode (exact_2k|comonotonic_bound)
- [ ] context_digest = sha256 over canonical JSON (sorted keys); raw context NEVER stored — test asserts absence
- [ ] Check entries reference describe() output (model pins ride along)
- [ ] Sink protocol (write/read/query) + SQLiteSink (default) + JsonlSink; Postgres confirmed OUT (parking)
- [ ] Atomic per-record writes; LogWriteError is loud; verdict still returns to caller

Outcome callback:
- [ ] report_outcome(record_id, ok, detail) — idempotent, last-write-wins, revision counter
- [ ] UnknownRecord actionable error; conventional keys documented (user_edit_distance, employer_response)

Audit CLI (the `governor` console script):
- [ ] export: records.jsonl + schema.json + pins.json + config.json (--redact-costs flag) + manifest.json (per-file sha256 + bundle sha256 + tool version + timestamp)
- [ ] verify: hash recompute → schema validation → deterministic re-derivation incl.
      max(D_det,D_all) and ceiling logic → stored-vs-recomputed comparison
- [ ] Output format exactly: "N records · N deterministic verdicts recomputed · M mismatches · pins listed · config digest matches · PASS/FAIL"; exit 0 only on PASS
- [ ] Verify states explicitly: model-backed checks re-verified from stored results, not re-run

Monitor hook:
- [ ] gov.monitor(sink, every=...) — rates by decision, per-check triggers, abstention-trend flag,
      outcome-reported fraction, credibility-weighted context rates (Z shown)
- [ ] TelegramSink (HTTP, no SDK) + CallbackSink for tests; scheduling documented as caller's job

actuarial.py (EXPERIMENTAL marker in module docstring):
- [ ] ibnr_ultimate: chain-ladder over reporting delays; factors exposed; synthetic-data tests
- [ ] time_to_outcome: Kaplan-Meier with censoring; median + dormant-after quantile;
      docstring states "Cox covariates: v0.2"

## Gate (run and record)

- [ ] Round-trip: suite-exported bundle verifies with ZERO mismatches
- [ ] Mutation test: flipped decision in copied bundle is CAUGHT (record_id + fields printed)

**Gate result:** ____ (PASS/FAIL) — **Date:** ____ — **Descopes taken:** ____
**Notes / resolutions (with reasons):**
