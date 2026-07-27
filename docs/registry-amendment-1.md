---
## Registry Amendment 1 — Scope Freeze Declaration
**Declared Sunday, July 26, 2026** (one day after the July 25 calendar date; 
delay noted, no scope consequences — no additions were accepted in the gap).

The contents of this guide as of Amendment 1 are FINAL for v0.1.0. From this 
declaration forward, no deliverable enters any card. New ideas, however good, 
go to Part VI (the parking list) in writing, with a reopening condition. 
Changes to existing scope flow only through the descope ladder (Part IV) or 
a written amendment at a Sunday review.

Amendments to date, absorbed before this freeze and already reflected in the 
cards: Check.run typed `output: Any`; examples/agent_tool_gate.py added to 
G-7 and the floor; G-2 aggregate policy boundary (judge_gate) with structural 
max(D_det, D_all) enforcement, per accepted review findings P1×3/P2×2; 
comonotonic upper bound replacing Poisson fallback at >12 checks (conservative, 
tighten-biased — requirement amended with rationale in docs/G2-checklist.md).

## Part VI Additions — Parking List Update (July 26, 2026)

**Learned outcome-risk model (LightGBM).** Supervised risk refinement over 
decision-log features; monotonic in check scores, SHAP-evidenced, pinned 
model files; subject to tighten-only like all learned components. 
Reopening condition: ≥1,000 labeled outcomes from the First-Qualified pilot.

**Issue templates (.github/ISSUE_TEMPLATE/).** Bug / feature / question. 
Reopening condition: any time before the August 8 announcement; cosmetic.

**ThresholdPolicy default re-derivation.** Replace the declared placeholders 
(0.25/0.60) with values derived from the pilot's empirical risk-score-vs-
outcome distribution. Reopening condition: pilot outcome data sufficient for 
a calibration read; pairs naturally with the calibration card.

**DecisionOS umbrella brand.** Any use of the DecisionOS name for a platform 
or company layer above Decision Governor. Reopening condition: NIW 
adjudication complete. Until then: one name, everywhere, matching the filing.

**Formal verification of composition proofs.** Mechanize the _compose 
invariants (determinism, order-invariance, tighten-only, ALLOW-requires-
deterministic) in a proof assistant; property tests remain the guarantee 
until then. Reopening condition: post-v0.2, or a contributor with the 
toolchain appears.
