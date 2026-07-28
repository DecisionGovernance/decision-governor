# Sunday Review 1 — July 26, 2026

First scheduled review. Absorbs the scope freeze, both amendments, the
parking additions, one interior-contract clarification, and the gate
statuses, in one sitting.

## Scope freeze

Registry Amendment 1 (docs/registry-amendment-1.md) declared July 26 —
one day after the July 25 calendar date, delay noted, no scope
consequences (no additions accepted in the gap). Amendment 2
(docs/registry-amendment-2.md) supplements it: Part II updated for the
pre-freeze additive extensions (Policy.judge_gate, the extended risk
block, the aggregate reasons line — schema remains v1.0), and the G-4
Cox-to-Kaplan-Meier scope amendment recorded with rationale instead of
staying a silent substitution. The freeze is binding: new ideas get one
line in Part VI with a reopening condition, nothing else.

## Parking list

Nine entries added across the two amendments, each with a reopening
condition (a decision with a trigger, not a graveyard entry): LightGBM
outcome-risk model; issue templates; ThresholdPolicy default
re-derivation; DecisionOS umbrella brand; formal verification of the
composition proofs; Postgres/pluggable sink; recalibration machinery
(Platt/isotonic/conformal); trained claim detection; Cox covariates.
The pre-existing perceptual-checks entry stands as the
modality-extensible line. Mirrored in
.github/skills/decision-governor-v0-2-parking/SKILL.md.

## Interior-contract clarification: decided_by

The G-2 review surfaced that "ceiling" could name two different
mechanisms at different layers. Resolved semantics, to implement when
G-4 makes the field durable:

- decided_by in {per_check, aggregate, ceiling}, where **ceiling means
  the engine's no-deterministic-evidence SCALE cap exclusively**
  (composition clause 3).
- The policy's CVaR allow-bar stays what it already is: the separate
  allow_barred_by_ceiling boolean inside the risk block — a
  policy-level fact that can be true even when decided_by is
  "aggregate".
- When multiple mechanisms bind at the same severity, record the most
  structural one: ceiling > aggregate > per_check. The audit reader
  wants the constraint that was *decisive*, not merely present.

G-4 fixture requirement: one record asserting each of the three values.

## Gate statuses

- G-0: executed (docs/G0-checklist.md); main is in sync with origin, so
  the push is verified as of this review.
- G-1: PASSED — gate recorded July 25 (docs/G1-checklist.md), 16 tests;
  the frozen-positional-API review finding fixed same day.
- G-2: PASSED — July 25–26 (docs/G2-checklist.md), five review findings
  resolved across three rounds (P1x3, P2x2), including the aggregate
  policy boundary with structural max(D_det, D_all) enforcement; 43
  tests at close.
- G-3: BUILT AHEAD OF WINDOW, gate tail outstanding — fixtures green
  (87 tests at record time, docs/G3-checklist.md); the embedder/NLI
  seams are injectable by design so the fixtures run without model
  downloads; the pin-freeze run (real revision + sha256 digests via the
  one-time [llm] download) is the recorded tail before the card is
  fully closed.
- G-4 through G-8: pending; execution-record checklists pre-staged in
  docs/.

## Registry mechanics — found at this review's verification pass

1. .gitignore ignored .github/skills/ wholesale, so every registry
   skill — including the contracts guardian the freeze depends on — was
   invisible to git while the freeze commit's message claimed the
   contracts skill was committed. Corrected at this review: the ignore
   line is removed; the skills enter the freeze-completion commit.
2. The registry-freeze-v0.1 tag was placed on d647184 before this
   review entry existed and before the skills were trackable — i.e.,
   before the kit was whole, contrary to the declared ordering rule
   (tag last, once). d647184 is already pushed; the tag is local.
   Corrective action: complete the kit in a follow-up commit (this
   review, the skills, the G-3 record), then move the still-local tag
   to the completion commit before any tag push. A tag becomes
   unforgeable only when pushed; moving it before that is correction,
   not revision.

## Next

G-4 (registry window August 1–4): the SQLite log, outcomes, audit
export/verify — where decided_by lands with its three fixtures, checks
get somewhere permanent to write evidence, and the compliance profile's
decision_logging rows flip to covered.
