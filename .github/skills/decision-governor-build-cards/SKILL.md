---
name: decision-governor-build-cards
description: "Use when: implementing or reviewing Decision Governor v0.1.0 build cards G-0 through G-8, including packaging, core engine, risk, checks, instrumentation, adversarial tools, inclusive checks, integrations, docs, and publication."
argument-hint: "Provide the card ID and current implementation status"
---

# Decision Governor Build Cards

## Purpose

Execute v0.1.0 in dependency order. Finish each card's verification gate before declaring it complete, and preserve the explicitly stated descopes.

## Card Procedure

1. Select the active card and identify its acceptance gate.
2. Implement the listed steps in order, using typed, testable public interfaces.
3. Add focused fixtures or property tests matching the card's risk.
4. Run the card gate and record failures or descope decisions in the build guide at the scheduled review.
5. Do not pull work forward from a later card unless it directly unblocks the active card.

## Card Summary

| Card | Deliverable | Completion Gate |
| --- | --- | --- |
| G-0 | Typed package skeleton, packaging, CI, quality files | Editable install succeeds and CI is green |
| G-1 | Engine, composition, Governor, decorator | Twelve-line quickstart and property tests pass |
| G-2 | Costs, CVaR, credibility, ruin stub | Worked values reproduce hand calculation |
| G-3 | Safety, fairness, compliance checks, registration | Fixtures pass and model pins verify |
| G-4 | SQLite log, outcomes, export/verify, monitors, actuarial | Export/verify round trip has zero mismatches |
| G-5 | Injection, shift, cascade, calibration, CI action | Bundled gate produces documented report artifact |
| G-6 | Deterministic HTML WCAG basics and roadmap | One HTML gating example works |
| G-7 | FastAPI, optional LLM, agent demo, First-Qualified | Published-package records export and demo prints four fates |
| G-8 | Docs, report, package publication | Clean-machine stranger completes the release journey |

## Required Technical Checks

- G-1 composition must be deterministic, order-invariant, and tighten-only under randomized check outputs.
- G-2 must cover zero observations, single-check, and equal-cost degenerate cases.
- G-3 must provide `protected_attribute_leak`; `verdict_disparity` may move to v0.1.1 only.
- G-4 verification must recompute deterministic verdicts from an audit bundle alone.
- G-5 protects cascade and calibration; shift descopes before injection.
- G-6 native alt text, contrast arithmetic, and label association checks cannot descope; axe-core may.

## G-3 Internal Design Delta: Embedder Seam

This is a Layer-3 internal design change: it adds no card deliverable, leaves
the G-3 gate unchanged, and requires no contract amendment ceremony.

- `checks/_models.py` owns both the existing pin registry and the minimal
	internal `Embedder` protocol: `modality`, `embed(items)`, and `describe()`.
	`embed()` returns one fixed-dimension vector per item. Keep batching and
	distance semantics out of the interface: checks own scoring so replacing an
	embedder cannot silently replace a check's meaning.
- `describe()` is mandatory. Each embedding check copies its embedder's pin
	block (repo, revision, sha256, modality) into its own `describe()` result,
	including for third-party embedders, so audit bundles retain model
	provenance.
- `PinnedTextEmbedder` is the shipped default, with `modality = "text"`. It
	wraps the pinned MiniLM's lazy download, verification, and memoization, and
	default consumers share that instance so weights load once.
- Do not generalize NLI: claims entailment remains a direct pinned text model.
	It has no v0.1 cross-modal analogue, and the seam applies only to embedding
	consumers.
- `style_drift` accepts an `Embedder` and checks `modality_of(output, context)`
	before embedding. The output's string `modality` declaration takes
	precedence, followed by context's string `output_modality`; strings and
	objects with `.text` retain the zero-configuration `"text"` convenience.
	The system never guesses from opaque payloads: undeclared inputs are
	`"unknown"` and skip with both modalities in the reason. A declared
	non-text output reaches its matching custom embedder as its native object.
- `claims_supported` uses the same embedder seam only for top-k fact
	retrieval. It must apply its text modality guard before retrieval; NLI stays
	unchanged.
- Preserve the composition invariant in a nearby code comment: when every
	check skips, the gate has no deterministic evidence, so ALLOW is unreachable
	and the verdict is capped at SCALE. Unknown modalities must skip safely,
	never crash or rubber-stamp an output.

### G-3 Seam Fixtures

In addition to the normal G-3 fixtures, require all of the following:

- `test_unknown_modality_caps_at_scale`, proving an all-skipped unknown-modal
	input cannot receive ALLOW.
- `FakeEmbedder(modality="audio")` fixtures proving both output and context
	modality declarations reach the custom embedder and score a native audio
	payload; the check's `describe()` result must carry its pin block.
- A regression assertion that the shipped text fixtures retain identical
	scores across the seam refactor.

Record this exact implementation note in `docs/G3-checklist.md`:

> Embedder seam introduced (Layer-3 internal): style_drift + retrieval parameterized, PinnedTextEmbedder default, NLI deliberately excluded; text-path score equivalence asserted.

Second modalities remain parked. The Part VI parking entry must describe
modality-extensible checks, name CLAP and CLIP as candidate audio and image
models, and reopen only at v0.2+ when there is a non-text-generating
deployment and a pinning budget.

## Documentation Discipline

Implement documented examples as executable tests where practical. Label actuarial methods as implemented, experimental, or specified future work accurately. A claim belongs in public documentation only after its associated acceptance gate passes.