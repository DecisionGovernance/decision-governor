# Card G-7 — execution record (Integrations + First-Qualified wiring)

**Registry window: Aug 3–6. Gate: FQ's package builder produces decision records through the released library; records appear in an exported, verified bundle; agent example prints its four fates. Agent example + FQ wiring are FLOOR.**

## Execution checklist

fastapi.py ([fastapi] extra; no top-level FastAPI import):
- [ ] GovernorMiddleware(app, governor_factory, deployment) — request-scoped via Depends(get_governor)
- [ ] Records tagged with deployment + request-correlation id
- [ ] Optional /governor/health: check registry, policy class, sink status — NO record contents

llm_judge.py ([llm] extra, lazy imports):
- [ ] Constructor REFUSES floating model aliases ("latest", bare family names) — hard error with explanation
- [ ] deterministic=False HARDCODED, not a parameter (tighten-only stratum not configurable)
- [ ] Provider interface: complete(prompt, model, temperature=0); adapters: OpenAI-compatible endpoint + Anthropic (~30 lines each)
- [ ] temperature 0; constrained JSON response parsed defensively; FULL prompt + raw response into evidence

Agent example:
- [ ] examples/agent_tool_gate.py green against final API (imports updated if paths shifted)
- [ ] Added to examples smoke-test runner in CI; four fates asserted in stdout

First-Qualified wiring (integration branch, FQ repo):
- [ ] Package builder imports the library (path/git dep → PyPI pin after G-8)
- [ ] Cover-letter gate: four checks + ship-spec CostStructure; SCALE → review queue
- [ ] report_outcome wired from review queue (edit distance) + outcome tracker (employer response)
- [ ] One real profile end-to-end → bundle exported → verify PASS
- [ ] DATE "running in production" became literally true: ____ (the WhatsApp-post honesty check)

## Gate (run and record)

- [ ] All three gate clauses green (FQ records in verified bundle; agent example fates printed)

**Gate result:** ____ — **Date:** ____ — **Descopes taken:** ____
**Notes:**
