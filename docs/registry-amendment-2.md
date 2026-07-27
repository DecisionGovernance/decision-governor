## Registry Amendment 2 — Freeze Supplement (July 27, 2026)

**Part II updated (pre-freeze additive extensions, schema remains v1.0):**
Policy protocol: optional judge_gate(records, context) -> Decision added 
per accepted finding P1; engine enforces max(D_det, D_all) structurally. 
Record schema risk block extended: gate_cvar, decided_by 
(per_check|aggregate|ceiling), allow_barred_by_ceiling, ceiling_fraction, 
enumeration mode. Verdict.reasons renders the aggregate line when the 
gate-level decision exceeds per-check composition.

**Scope amendment (G-4):** "Cox time-to-outcome" delivered in v0.1 as 
Kaplan–Meier with censoring; Cox covariate modeling deferred. Rationale: 
covariate modeling requires outcome data the pilot has not yet produced; 
KM is the honest estimator at current evidence. Docstring states the 
deferral; parking entry below.

**Part VI additions:** Postgres/pluggable production sink (reopen: first 
deployment outgrowing SQLite). Recalibration machinery — Platt/isotonic/ 
conformal over check scores (reopen: labeled outcomes sufficient for a 
reliability fit; pairs with threshold re-derivation). Trained 
claim-detection model replacing greedy heuristics (reopen: v0.2, with 
pinning budget). Cox covariate time-to-outcome (reopen: pilot outcome 
volume supports covariates).
