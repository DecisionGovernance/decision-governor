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

First-Qualified wiring (integration branch, FQ repo):
- [ ] Package builder imports the library (path/git dep → PyPI pin after G-8)
- [ ] Cover-letter gate: four checks + ship-spec CostStructure; SCALE → review queue
- [ ] report_outcome wired from review queue (edit distance) + outcome tracker (employer response)
- [ ] One real profile end-to-end → bundle exported → verify PASS
- [ ] DATE "running in production" became literally true: ____ (the WhatsApp-post honesty check)

## Gate (run and record)

- [ ] All three gate clauses green (FQ records in verified bundle; agent example fates printed)
      — library-side clause (agent example fates in CI) green Aug 2, 2026; the two FQ
      clauses await the FQ-repo acceptance run

**Gate result:** LIBRARY SIDE COMPLETE, FQ WIRING PENDING — **Date:** Aug 2, 2026 (library side) — **Descopes taken:** none (FQ wiring is cross-repo work, not a descope; it is the remaining floor)
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
8. FQ wiring (Steps 5–7) is cross-repo work on the FQ integration
   branch and remains open above. Protected explicitly per the card:
   Step 7 must be a REAL profile through the REAL gate producing a
   real, verifiable record — the G-7 gate criterion, the
   truth-condition for the launch post's "running in production"
   claim, and Section 6's deployment description all depend on that one
   run. It must not be simulated; the date line above stays blank until
   it happens.

Gate evidence (Aug 2, 2026, library side): full suite green including
33 new G-7 tests (extras blocking, middleware scoping/correlation/
health, judge guards/degradation/providers, the real-FastAPI Depends
path, and the four-fates-plus-bundle round trip); the agent example
prints ALLOW / SCALE(manager_approval_queue) / ABSTAIN /
SCALE(soft_delete_with_review) and its bundle verifies:
"4 records · 4 deterministic verdicts recomputed · 0 mismatches · PASS".
