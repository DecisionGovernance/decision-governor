# Card G-7 — execution record (Integrations + First-Qualified wiring)

**Registry window: Aug 3–6. Gate: FQ's package builder produces decision records through the released library; records appear in an exported, verified bundle; agent example prints its four fates. Agent example + FQ wiring are FLOOR.**

## Execution checklist

Extras discipline (Step 0):
- [x] No optional dependency imported at package top level — `decision_governor`,
      `decision_governor.integrations.*` import cleanly with fastapi/starlette/pydantic/
      openai/anthropic/HF ALL blocked (test_base_package_imports_with_every_optional_dependency_blocked
      runs a subprocess with a blocking meta-path finder)
- [x] Judge provider SDKs (`openai`, `anthropic`) added to the `[llm]` extra; `[fastapi]`
      unchanged; packaging test asserts both extras in the built wheel's METADATA

fastapi.py ([fastapi] extra; no top-level FastAPI import):
- [x] GovernorMiddleware(app, governor_factory, deployment) — request-scoped via Depends(mw.get_governor)
- [x] Records tagged with deployment + request-correlation id
- [x] Optional /governor/health: check registry, policy class, sink status — NO record contents

llm_judge.py ([llm] extra, lazy imports):
- [x] Constructor REFUSES floating model aliases ("latest", bare family names) — hard error with explanation
- [x] deterministic=False HARDCODED, not a parameter (tighten-only stratum not configurable)
- [x] Provider interface: complete(prompt, model, temperature); adapters: OpenAI-compatible endpoint + Anthropic (~30 lines each)
- [x] temperature 0; constrained JSON response parsed defensively; FULL prompt + raw response into evidence

Agent example:
- [x] examples/agent_tool_gate.py green against final API (imports updated; explicit cost_map added)
- [x] Added to examples smoke-test runner in CI; four fates asserted in stdout
      (test_agent_example_prints_its_four_fates_and_round_trips_the_bundle, which also
      exports the run's decisions and asserts `verify` PASSes)

First-Qualified wiring (integration branch, FQ repo `fq_pilot` @ `80d555b5`):
- [x] Package builder imports the library — pinned to COMMIT
      `4ef34fd4837939ab966503592c3149955e1a20cc`, not a branch, in both
      `pyproject.toml` and `requirements.txt`; `first_qualified/govern.py` stamps the
      revision into every record's `deployment` field, so each record carries the
      build that produced it (FQ spec Amendment 3). The PyPI pin swap to `==0.1.0`
      is already carded on G-8. Records were produced through the PINNED library,
      not a released one — see note 11
- [x] Cover-letter gate: FIVE checks (not four) + RECONCILED ship-spec CostStructure
      — `pii_leak`, `output_domain`, `claims_supported`, `style_drift`, plus a
      pilot-local deterministic `LetterLength`, because `OutputDomain` measures
      characters and cannot express the stated word contract (FQ spec Amendments 3
      and 4). More than carded, not less. Costs `100/100/8/3`
      (`unsupported_claim`/`pii_exposure`/`off_voice`/`abstention`), α = 0.05,
      `default_cost=None`. "Ship-spec" was reconciled, not adopted — see note 11
- [ ] SCALE → review-queue: **CONFIGURED, UNEXERCISED** — neither ticked nor
      descoped; recorded as unevidenced. See note 10
- [x] **DESCOPED from the G-7 floor:** `report_outcome` wiring from review queue
      (edit distance) + outcome tracker (employer response) — decision, reason and
      reopening condition in note 9. Zero matches for `report_outcome`,
      `edit_distance` or `employer_response` anywhere in the pilot; all ten records
      carry `execution_outcome.reported: false`. Genuinely unbuilt, and said so
- [x] One real profile end-to-end → bundle exported → verify PASS — EXCEEDED: ten
      real runs (six truthful, four adversarial), `artifacts/fq_bundle/` exported,
      `governor audit verify` **PASS ×2, identical output, exit 0 both times**
- [x] DATE "running in production" became literally true: **August 8, 2026**
      (acceptance session 00:48–00:50 UTC) — the WhatsApp-post honesty check

## Gate (run and record)

- [x] All three gate clauses green (FQ records in verified bundle; agent example fates printed)
      — library-side clause (agent example fates in CI) green Aug 2, 2026; the two FQ
      clauses green Aug 8, 2026 on the acceptance run recorded above

**Gate result:** MET — **Date:** Aug 8, 2026 (library side Aug 2, 2026) — **Descopes taken:** ONE — pilot outcome wiring (`report_outcome`, edit-distance, employer-response), reasoned and reopening-conditioned in note 9. Separately, SCALE → review-queue is recorded as configured-but-unexercised (note 10): neither a tick nor a descope, because nothing was cut and nothing was evidenced.
**Notes:**

1. Extras discipline enforced as a test, not a promise: a subprocess
   installs a meta-path finder that raises on every optional dependency
   (including starlette and pydantic, which fastapi would drag in) and
   then imports the package plus both integration modules. Lazy imports
   live inside `GovernorMiddleware.__init__` (forgiving — the class
   stays usable against duck-typed apps) and inside the provider
   adapters' `_resolve_client` (hard error with the
   `pip install "decision-governor[llm]"` hint).
2. Factory, not instance, as carded: `get_governor` builds a fresh
   governor per request, stamps `deployment`, mints or propagates the
   `x-correlation-id` header, and binds both into every evaluate()
   context (setdefault — endpoint-supplied keys win). The correlation
   id is additionally stamped onto the stored record as a top-level
   `correlation_id` key by a decorating sink, so a web request maps to
   its governance decisions in the audit bundle. Schema v1.0 validates
   required keys only; the extra key rides through export/verify
   untouched (asserted by test).
3. The health route exposes structure only — deployment, sorted check
   names, policy class name, sink liveness — and a test evaluates a
   distinctively-marked payload first, then asserts the marker cannot
   appear anywhere in the health JSON.
4. The judge's two hard rules are structural: `deterministic` is a
   read-only property (assignment raises AttributeError; there is no
   constructor parameter to promote it), and `is_floating_alias`
   rejects anything without a dated suffix (20241022 / 2024-10-22) or a
   sha256 digest (the Ollama `name@sha256:` form — which also keeps the
   no-external-keys local-model path alive alongside the
   OpenAI-compatible adapter's `base_url`). A structural test registers
   a judge that returns a perfectly clean verdict and asserts the
   decision is still SCALE, decided_by "ceiling".
5. Judge degradation is conservative and loud, never a crash: a
   provider exception or malformed (non-JSON) response yields
   score=1.0, confidence=0.3 with the failure named in evidence — the
   judge told us nothing, so it must not look clean, and being
   non-deterministic it cannot authorize anything either way. Clean
   responses log the FULL prompt and raw response into evidence per the
   card: the judge's reasoning is auditable, not a black box.
6. The agent example needed two updates to be green against the final
   API: `CheckResult` now imports from the package top level, and
   CVaRPolicy's explicit-cost-map requirement (no silent defaults)
   meant naming each check's cost. One re-pricing with the reason
   recorded: the deletion cost is now `hasty_deletion=6.0` rather than
   `irreversible_loss=1000.0`, because verdicts are monotone in mapped
   cost under a single policy — a 1000-unit cost rationally ABSTAINS
   rather than SCALEs against a 5-unit abstention, and the card's
   intended fate for the user-requested delete is SCALE (soft-delete).
   The honest framing, now in the example's comments: this deployment
   keeps a soft-delete window, so the data is recoverable and what a
   bad deletion actually costs is the skipped review. Price the failure
   you would actually eat.
7. The four-fates test runs the example as a subprocess (the same
   `python examples/agent_tool_gate.py` a reader would run), asserts
   all four fates in stdout, then exports the decisions it just logged
   and asserts `verify` PASSes — the library-side half of gate clause
   (2) held end-to-end.
8. FQ wiring (Steps 5–7) was cross-repo work on the FQ integration
   branch — CLOSED Aug 8, 2026; see notes 9–13. Protected explicitly
   per the card: Step 7 must be a REAL profile through the REAL gate
   producing a real, verifiable record — the G-7 gate criterion, the
   truth-condition for the launch post's "running in production"
   claim, and Section 6's deployment description all depend on that one
   run. It must not be simulated; the date line above stays blank until
   it happens. It was not simulated: ten real generations through the
   real gate, and the date line is now filled from the acceptance
   session that produced them.

9. **Descoped from the G-7 floor: pilot outcome wiring
   (`report_outcome`, edit-distance, employer-response).** Reason:
   outcome reporting is post-decision instrumentation requiring product
   surface (a review queue) that is Layer A scope; the library callback
   itself is built and tested (G-4). Collecting hollow outcomes —
   outcomes reported by nobody about nothing — to tick the clause would
   contradict §5.4's honestly-undefined calibration statistic ("0
   reported outcomes — statistic undefined, not zero") and undercut
   §10.1's cold-start argument. Nothing in the launch claim depends on
   it: the claim is generate → gate → record → export → verify, and all
   five verbs are evidenced. **Reopening condition:** Layer A's review
   queue — the first surface where a human action generates a real
   outcome — at which point the wiring is an afternoon and the
   calibration path (§10.1/§10.2) begins consuming its output.

10. **SCALE → review-queue: configured and passed on all runs
    (`scale_path="review-queue"`, `pilot_run.py:41` and `:71`),
    unexercised — zero SCALE verdicts produced.** All ten verdicts were
    ABSTAIN and all ten records store `scale_path: None`. The route
    exists in code with no records demonstrating it. Unexercisable under
    the shipped calibration: NEUTRAL carries weight 0.6 and every run
    contains at least one neutral span, so `0.6 × 100` against
    `abstention = 3.0` at α = 0.05 abstains every time; SCALE evidence
    arrives only with outcome-calibrated thresholds. Recorded as
    unevidenced, NOT as working — a route with zero records does not get
    described as functioning. §6.4's scope paragraph carries the
    matching line.

11. Two wording precisions, both narrowing a claim to its evidence.
    (a) "Through the PINNED library (`4ef34fd48379`)", not "the released
    library" as the card reads: `decision-governor` is `0.1.0.dev0` and
    unpublished until G-8, so records were produced through a pinned
    commit. The pin swap to `==0.1.0` is already on the G-8 checklist.
    (b) "RECONCILED ship-spec CostStructure", not "ship-spec": the spec
    stated the schedule twice and inconsistently (`100/8/3` in one place,
    `100/100/3` in another) and priced only two of the registered checks,
    which `CVaRPolicy` rejects outright with `UnmappedCheck` when
    `default_cost` is None. FQ spec Amendment 2 resolved it to
    `100/100/8/3` against the technical report's published fixture, and
    did so BEFORE any acceptance evidence was collected — the ordering
    that makes the evidence admissible. Likewise "five checks", not
    four, per FQ spec Amendments 3 and 4.

12. What the ten runs actually measured, at the numbers rather than the
    prediction. **Verdicts are scenario-invariant:** all six truthful
    runs abstain whether the posting asks 1+, 6+ or 10+ years, so the
    verdict does not track the job. **ENTAILED count separates the
    populations; the score does not** — truthful runs carry 2–3 ENTAILED
    spans and zero CONTRADICTED, adversarial runs carry zero ENTAILED
    and CONTRADICTED in 3 of 4, while the claims scores overlap at the
    boundary (truthful 0.491–0.598, adversarial 0.598–0.967). **Fabricated
    credentials are positively identified in 3 of 4 attempts** —
    sensitivity is 3/4 at the run level, with one false negative (run
    `2f403876`, "over a decade of hands-on experience" scored NEUTRAL
    0.59 where the same fabrication class scored CONTRADICTED 0.81 in two
    other runs). The check is therefore NOT described as reliably
    catching invented seniority. **No false positives this session:**
    zero CONTRADICTED spans across all six truthful runs. **ALLOW remains
    unreachable for realistic letters** — the library's deliberate
    "neutral is not innocent" posture, not a defect, but the gate cannot
    certify honest prose. The three deterministic checks allowed all ten
    runs (132–248 words inside the 80–350 contract).

13. Amendment namespaces do not collide, and citations must say which.
    "FQ spec Amendments 1–5" are declared in the pilot's
    `.github/skills/first-qualified-pilot/SKILL.md` and are distinct from
    this registry's Amendments 1–2 (`docs/registry-amendment-1.md`,
    `-2.md`), which cover the scope freeze and the judge_gate/Kaplan–Meier
    supplement. Every amendment cited in this entry is an FQ spec
    amendment and is labeled as such.

Gate evidence (Aug 2, 2026, library side): full suite green including
33 new G-7 tests (extras blocking, middleware scoping/correlation/
health, judge guards/degradation/providers, the real-FastAPI Depends
path, and the four-fates-plus-bundle round trip); the agent example
prints ALLOW / SCALE(manager_approval_queue) / ABSTAIN /
SCALE(soft_delete_with_review) and its bundle verifies:
"4 records · 4 deterministic verdicts recomputed · 0 mismatches · PASS".

Gate evidence (Aug 8, 2026, 00:48–00:50 UTC, FQ side): ten real
cover-letter generations (Gemini `gemini-3.5-flash-lite` — FQ spec
Amendment 1, which demonstrates the governance layer's
provider-agnosticism rather than asserting it: the spec originally
specced Claude, the pilot ran Gemini, the gate configuration is
unchanged) through the five-check gate at `governor=4ef34fd48379`,
exported to `artifacts/fq_bundle/` and verified twice with identical
output: "10 records · 10 deterministic verdicts recomputed · 0
mismatches · pins: claims_supported, letter_length, output_domain,
pii_leak, style_drift · config digest matches · 20 model-backed check
results re-verified from stored CheckResults — the models are not in the
bundle · PASS". Model and Governor configuration constant across all ten
records; prompt-variant and scenario provenance differ per record by
design, which is what lets the bundle substantiate its own labels. All
ten verdicts ABSTAIN. Full matrix, per-record ids and findings:
`fq_pilot/RUN_RECORD.md` @ `80d555b5`.
