# Card G-6 — execution record (Inclusive Deployment Gate)

**Registry window: Aug 4–5, TIMEBOXED ONE DAY. Gate: one documented example gates a generated HTML snippet. Pre-authorized descope: axe adapter → v0.2. Native checks + roadmap page CANNOT descope ("commenced" must be literally true).**

## Execution checklist

wcag.py (three native deterministic checks, standard Check protocol):
- [ ] alt_text_presence — stdlib html.parser (no bs4 dependency); every <img> non-empty alt
- [ ] contrast_arithmetic — WCAG ratio where fg/bg statically extractable; worst pair vs 4.5:1;
      non-extractable elements: evidence says "not statically checkable", element skipped (honesty over pretense)
- [ ] label_association — label[for] / aria-label / aria-labelledby on form inputs
- [ ] All three registerable at ABSTAIN grade via normal cost mapping (test with a cost_map entry)

axe.py:
- [ ] Node detected at import; clear degradation message if absent
- [ ] (or) DESCOPED to v0.2 per pre-authorization — record the decision below

Docs:
- [ ] docs/inclusive-roadmap.md — what full 508 validation adds; v0.1 stated as the commenced minimal gate
- [ ] Worked example: generated HTML email template; ABSTAIN shown on missing alt

## Gate (run and record)

- [ ] The documented example gates the HTML snippet end-to-end

**Gate result:** ____ — **Date:** ____ — **Timebox honored (Y/N):** ____ — **axe adapter:** shipped / descoped
**Notes:**
