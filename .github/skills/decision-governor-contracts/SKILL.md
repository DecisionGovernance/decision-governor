---
name: decision-governor-contracts
description: The frozen public contracts of decision-governor, the four-layer rigidity stratification, and the change ceremony. MUST be read before modifying anything in decision_governor/core/, decision_governor/risk/, the record schema, or any test in tests/test_engine.py or tests/test_contracts.py. If a task appears to require changing a frozen or interior contract, STOP and follow the ceremony at the bottom instead of implementing.
---

# Decision Governor — Contracts & Change Ceremony

This project develops against a frozen registry (see decision-governor-build-cards
and decision-governor-release-governance). Scope froze July 26, 2026 (Registry
Amendment 1). This skill defines what is frozen, how frozen, and the only
legitimate ways anything changes.

## The four-layer rigidity stratification

Every definition in this codebase lives in exactly one layer. Before changing
anything, identify its layer; the layer determines the ceremony.

**Layer 1 — Declared contracts (maximum rigidity).** The three public
definitions in Part II of the consolidated guide: the Decision enum, the
Check protocol + CheckResult, and the decision-record schema (v1.0). Frozen
by declaration. Any change is a breaking change: version bump, CHANGELOG
entry, migration note, written amendment at a Sunday review. An agent NEVER
changes these on its own judgment.

**Layer 2 — Interior contracts (frozen by dependency).** Not declared in
Part II but load-bearing across cards, frozen the moment their card's gate
passed: the Policy protocol (judge, and the optional judge_gate added by
accepted finding P1), the Verdict/GateResult/CheckRecord shapes, the
composition operator's three clauses, the severity ordering, and the
max(D_det, D_all) aggregate enforcement. Same ceremony as Layer 1, by
dependency rather than declaration.

**Layer 3 — Card deliverables (frozen as behavior).** Everything a passed
card's gate verified. Internals may be refactored freely PROVIDED the full
test suite stays green — the G-1 property tests are the tripwire. A refactor
that requires changing a test's assertion is not a refactor; it is a Layer 1/2
change wearing a disguise. Stop and follow the ceremony.

**Layer 4 — Reference defaults (free).** Tunable values documented as
placeholders: ThresholdPolicy's 0.25/0.60, scale_mitigation 0.3,
ceiling_fraction 0.5, monitor cadences. Changeable with a one-line CHANGELOG
entry and a reason; observable default changes ride a minor version.

## The frozen contracts, verbatim

### Decision (Layer 1)

ALLOW ("allow") < SCALE ("scale") < ABSTAIN ("abstain"), strict severity
order. This vocabulary is in a federal filing. It does not change. Ever.

### Check protocol + CheckResult (Layer 1)

Check: `name: str`, `deterministic: bool`, `run(output: Any, context: Mapping)
-> CheckResult`. `output` is Any by design — gates govern decisions, not
documents. `deterministic` governs tighten-only treatment and is a property
of the check's NATURE, never a configuration knob (see llm_judge: hardcoded
False). CheckResult: `score: float [0,1]`, `confidence: float [0,1]`,
`evidence: list[str]`; bounds enforced at construction.

### Decision record schema v1.0 (Layer 1, as extended pre-freeze by Amendment 2)

Fields: record_id, schema_version, timestamp, gate, checks[] (name, score,
confidence, deterministic, evidence, describe-reference), risk {policy,
alpha, expected_costs, credibility {Z, n}, gate_cvar, decided_by
(per_check|aggregate|ceiling), allow_barred_by_ceiling, ceiling_fraction,
enumeration mode}, decision, scale_path, context_digest, execution_outcome.
context_digest is sha256 of canonical JSON; RAW CONTEXT IS NEVER STORED.

### Policy protocol (Layer 2)

`judge(check_name, result, context) -> Decision` required;
`judge_gate(records, context) -> Decision` optional. When judge_gate exists,
the engine computes D_det = judge_gate(deterministic records only) and
D_all = judge_gate(all records) and takes the severity max of both plus the
per-check composition. Policies judge; ONLY the engine composes.

## The composition invariants (Layer 2 — the project's spine)

1. Composition is deterministic and order-invariant.
2. Worst-of: the most severe judgment prevails; verdicts never average.
3. Tighten-only, structural: the deterministic base comes from deterministic
   checks alone; non-deterministic checks may only escalate; with zero
   deterministic evidence, ALLOW is unreachable (ceiling SCALE). A learned
   component can be the reason an action was constrained, never the reason
   one was authorized.
4. Aggregate tighten-only: max(D_det, D_all) is enforced by the ENGINE so
   even an adversarial policy cannot use a learned record's presence to relax
   a verdict (regression fixture: EvilPolicy).

These are verified by Hypothesis property tests (~200 examples per law).
If your change makes any property test fail, the change is wrong, not the
test. Do not weaken, skip, or re-scope a property test to make a build pass.

## The change ceremony

When a task appears to require changing Layer 1 or 2, or re-scoping a card:

1. STOP implementation.
2. Write a short proposal: what changes, which layer, why the registered
   scope cannot be satisfied without it, what breaks downstream.
3. Output the proposal separately, labeled "REGISTRY AMENDMENT PROPOSAL" —
   do not implement it, even partially, even behind a flag.
4. The maintainer accepts it as a dated amendment at a Sunday review (or
   rejects it to Part VI with a reopening condition). Only then implement.

Precedent showing the ceremony working: the G-2 aggregate-policy finding
(P1) was a proposal → accepted amendment → implementation → adversarial
regression fixture. That is the path. The anti-pattern it replaced: the
staged per-check implementation that satisfied G-1's letter while missing
G-2's requirement — caught precisely because the requirement was written.

## Standing rules for implementing agents

Implement exactly the card specification you were given. Anything you
believe should be added beyond it: list it separately as a parking-list
proposal (Part VI grammar: name, one paragraph, reopening condition) — do
not implement it. Every deliverable ships with tests; the card's gate
criteria are the acceptance tests. After any change, run the FULL suite —
the property tests are the tripwire for accidental invariant damage. Record
gate results and resolutions in docs/G{n}-checklist.md with dates. One
public name everywhere: decision-governor. No number is displayed that the
system cannot defend; no claim is written that is not literally true on the
day it is written.