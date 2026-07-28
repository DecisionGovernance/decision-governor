# Card G-3 — execution record

Steps executed in build order (deterministic-first, as planned):
1. Check base plumbing (checks/_base.py): CheckBase with describe() for
   the audit bundle's model-pins section, the standardized skip()
   constructor (score 0, confidence 1, "n/a: <reason>"), clamp01() so no
   check can emit an out-of-range score even by bug, extract_text for
   str / .text / arbitrary governed objects. Registration plumbing:
   default_checks() and register_default_checks() ship the deterministic
   trio.
2. pii_leak (checks/pii.py): pattern battery (emails, US and
   international phone formats, SSN-shaped strings, address heuristics)
   plus configurable custom terms from constructor AND context. Evidence
   is the MASKED span with offset — the check never reproduces the PII
   it caught into the log; even describe() ships custom terms masked.
   PII is binary: score 1.0, confidence 1.0.
3. output_domain (checks/domain.py): length bounds, required/forbidden
   sections, minimal JSON-schema subset (required + property types);
   constructor rules merge with context["domain_rules"]. Score is the
   fraction of rules violated — the one deterministic check where
   graduated score is natural — each violated rule named in evidence.
4. protected_attribute_leak (checks/fairness.py — the floor-protected
   one): term battery (age, family-status, nationality, religion,
   health) plus the inference screen for indirect leaks ("as a mother
   of", "my church", "despite my age"). Evidence names the CATEGORY,
   not just the term. Configurable per deployment; default strict.
5. Model pinning (checks/_models.py): PINS carry repo + revision
   (commit SHA — Hub repos mutate) + sha256 of weight files; verify()
   hard-errors naming BOTH hashes on mismatch; load() = download ->
   verify -> load -> memoize; unfrozen pins REFUSE to load so an
   unverified model can never participate in a verdict. Deviation from
   plan, recorded honestly: this build environment cannot download the
   pinned models (torch + DeBERTa are gigabytes), so revision/sha256
   ship as None with a freeze tool
   (python -m decision_governor.checks._models freeze <name>) that
   downloads once, computes the real digest, and prints the pin block
   to commit. Digests are computed from real weights, never invented.
   The verification machinery itself is fully unit-tested against
   local fixture files (success, mismatch naming both hashes, refusal
   on unfrozen pins, memoization, freeze).
6. style_drift (checks/style.py): distance to the centroid of
   context["style_refs"], calibrated against the user's own
   within-reference spread; confidence scales with sample count
   (min(1, n/5) — credibility-thinking inside a check); evidence speaks
   in the user's own baseline. Implementation decision: mean absolute
   deviation instead of median-based MAD — median-MAD collapses to 0
   on the 3-5-sample reference sets this check must serve (caught by
   the fixture, not by luck). Embedder injectable; defaults to the
   pinned model.
7. claims_supported (checks/claims.py): segment -> claim detection
   (declarative + first-person + verifiable content; opinion/aspiration
   skipped; biased toward OVER-detection because under-detection is the
   dangerous failure — stated in the docstring) -> top-k retrieval
   before NLI (miniature RAG; retrieved facts go into evidence) ->
   entailment with weights contradicted 1.0 / neutral 0.6 (neutral is
   not innocent) / entailed 0. Worst-claim-wins (max, not mean);
   confidence is the NLI probability on the deciding claim. NLI and
   embedder injectable; default to pinned models.
8. verdict_disparity (checks/monitors.py): a monitor, not a gate — it
   reads (cohort, decision) log records. Per-cohort constrained rates,
   credibility-weighted rates via Monday's Bühlmann–Straub (tiny
   cohorts shrink toward the collective instead of screaming, Z always
   visible), chi-squared with p-value computed via an in-package
   regularized incomplete gamma (base install stays scipy-free;
   verified against table critical values). Registers in MONITORS for
   G-4's instrumentation hook. Did NOT need the pre-authorized slip.
9. Compliance family (checks/compliance.py): the deliberately simple
   checklist runner (automated -> SDK capability; attested ->
   deployment attestation; everything else not_covered, stated
   plainly) plus the shipped NIST AI RMF profile
   (checks/profiles/nist_ai_rmf.yaml). decision_logging and
   adversarial_toolkit rows are deliberately not in SDK_CAPABILITIES
   until G-4/G-5 land — the fixture asserts those rows render
   not_covered TODAY and flip only when the capability is real. The
   honesty of the not_covered rows is what makes the covered rows
   credible.
10. The gate (tests/test_checks.py): known-good/known-bad fixture pair
    per check with exact evidence strings; the adversarial claims
    fixtures — exaggeration ("led" vs "contributed to" -> neutral
    0.71, the product's honesty in miniature), compositional smuggle
    (contradicted 0.83), clean paraphrase (must pass, guarding against
    over-zealousness), worst-claim-wins; the masked-evidence assertion
    (the log must not contain the caught PII); style same-author-
    different-topic passes while drifted output saturates; disparity
    flagged/not-flagged/tiny-cohort-shrunk; compliance statuses and
    the RMF honesty test; integration fixtures: one Governor with all
    applicable checks, good document ALLOW end-to-end, bad document
    ABSTAIN with pii_leak named in reasons (and the PII still masked).

Packaging: pyyaml added to base deps (profile loading); model deps
(huggingface_hub, sentence-transformers, transformers) land in the
[llm] extra; profiles ship as package data.

Embedder seam introduced (Layer-3 internal): style_drift + retrieval
parameterized, PinnedTextEmbedder default, NLI deliberately excluded;
text-path score equivalence asserted.

modality_of revised from central heuristic to declaration-precedence chain
(finding: heuristic defeated the Embedder seam's extensibility); fixtures
extended to exercise a non-text run end-to-end.

Registry ruling — modality extensibility (July 26, 2026): the
modality-agnostic analysis is ACCEPTED, split into two fates. In scope
for G-3 (Layer-3, implemented): everything the modality_of fix already
entails — the declaration-precedence chain (output declares itself,
then context's output_modality, then the text conveniences, else
"unknown" which skips safely rather than being guessed into a check),
the Embedder seam with its modality attribute and describe()
provenance, and the MediaOutput pattern shipped as
documentation-by-fixture (the AudioOutput frozen dataclass + modality-
aware FakeEmbedder in tests/test_checks.py: a declared audio output
runs end-to-end through a custom embedder, and — the sentence that
matters — a modality present ONLY through learned checks caps at SCALE
by the existing clause-3 machinery, no new rule needed; deterministic
evidence is what lifts to ALLOW, per-modality, not just per-gate).
PARKED for v0.2 (Part VI entry added): promoting MediaOutput to a
public exported helper plus a shipped DeterministicCheck example for
custom modalities — a public API surface is scope, however small;
reopening condition: first external user bringing a non-text modality,
or v0.2, whichever first. The pattern ships now as fixture; the
blessed public class waits for a real use case to shape it.

Docs caveat, recorded here for the G-8 "bring your modality" page:
deterministic checks on perceptual content verify *provenance and
form*, not *meaning* — "well-formed, from a signed source, on the
allowlist" is not "safe to show." Same honest boundary as text
(output_domain verifies shape, not truth; claims_supported needed a
closed fact source to verify meaning). The vault rule bounds *who* can
authorize; it never upgrades *what* the authorization means. The
three-line summary for that page: agnostic transport, yes; agnostic
embedding/scoring mechanics, yes; agnostic authorization from a model
embedding alone, no.

Gate result (July 26, 2026 — ahead of the July 29 window): 87 tests
passed (full suite), ruff clean, mypy clean (strict on core/ and
risk/), coverage 95% overall — the uncovered remainder is the model
download/load paths that require the [llm] extra and network, plus two
guards in the incomplete-gamma internals. Pin infrastructure verified
against local fixtures; real revision/sha256 digests await the
one-time freeze run on a machine with the [llm] extra — that run and
the committed pin blocks are the remaining G-3 tail, tracked here.
G-4's log now has a check library worth logging.

Release blockers closed (July 27, 2026 — review findings P1x2, P2x1):
1. The built wheel was broken while the source tree passed: no
   nist_ai_rmf.yaml inside (no package-data config), no pyyaml
   dependency (dev env had it incidentally), and the [llm] extra the
   error messages pointed at was empty. Fixed: pyyaml in base deps
   (the compliance runner is base functionality), package-data ships
   checks/profiles/*.yaml, [llm] carries huggingface_hub +
   sentence-transformers + transformers. A packaging smoke test
   (tests/test_packaging.py) now builds a REAL wheel and asserts the
   profile is inside and the metadata declares what the code imports —
   the source tree can no longer lie about the artifact. (The smoke
   test caught its own first bug: METADATA normalizes names to
   hyphens.)
2. The documented default backends could not run installed: pins ship
   unfrozen, so StyleDrift() / ClaimsSupported() failed at run() time.
   Resolved as the explicit descope already recorded in this file's
   tail, now enforced in code: non-injected defaults fail loud AT
   CONSTRUCTION with the freeze-or-inject message
   (_models.require_default_backend); fixtures assert both the refusal
   and that frozen pins restore default construction with loading
   still lazy. No silent landmines: the unavailable path is refused at
   the earliest possible moment.
3. Stale gate numbers corrected: as of this close-out the staged suite
   is 96 passed, ruff clean, mypy clean, coverage 95% (uncovered
   remainder unchanged in kind). The pin-freeze run remains the
   recorded G-3 tail.
