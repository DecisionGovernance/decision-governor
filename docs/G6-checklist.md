# Card G-6 — execution record (Inclusive Deployment Gate)

**Registry window: Aug 4–5, TIMEBOXED ONE DAY. Gate: one documented example gates a generated HTML snippet. Pre-authorized descope: axe adapter → v0.2. Native checks + roadmap page CANNOT descope ("commenced" must be literally true).**

## Execution checklist

wcag.py (three native deterministic checks, standard Check protocol):
- [x] alt_text_presence — stdlib html.parser (no bs4 dependency); every <img> non-empty alt
- [x] contrast_arithmetic — WCAG ratio where fg/bg statically extractable; worst pair vs 4.5:1;
      non-extractable elements: evidence says "not statically checkable", element skipped (honesty over pretense)
- [x] label_association — label[for] / aria-label / aria-labelledby on form inputs
- [x] All three registerable at ABSTAIN grade via normal cost mapping (test with a cost_map entry)

axe.py:
- [x] Node detected at import; clear degradation message if absent
- [x] (or) DESCOPED to v0.2 per pre-authorization — record the decision below

Docs:
- [x] docs/inclusive-roadmap.md — what full 508 validation adds; v0.1 stated as the commenced minimal gate
- [x] Worked example: generated HTML email template; ABSTAIN shown on missing alt

## Gate (run and record)

- [x] The documented example gates the HTML snippet end-to-end
      (examples/inclusive_html_gate.py; pinned by
      test_the_documented_example_gates_the_snippet_end_to_end)

**Gate result:** PASS — **Date:** July 29, 2026 (ahead of the Aug 4–5 window) — **Timebox honored (Y/N):** Y — **axe adapter:** descoped to v0.2 (shell shipped)
**Notes:**

1. Module layout as carded: inclusive/_html.py (the shared stdlib
   parsing seam, parsed once and feeding all three checks),
   inclusive/wcag.py (the three checks + the WCAG color math),
   inclusive/axe.py (the degrading shell). No bs4, no Node required —
   the base install's no-heavy-deps promise holds.
2. The axe decision, made explicitly: the shell ships (detects Node via
   shutil.which, skips cleanly with a stated reason whether Node is
   present or absent, describe() records node_detected and the stub
   status) and the subprocess runner is v0.2. Both skip messages name
   the descope so a registered axe_core check can never silently
   pretend it ran.
3. label_association checks the card's three explicit mechanisms PLUS
   the wrapping-<label> implicit association — also WCAG-recognized,
   and omitting it would false-fail `<label>Name <input></label>`,
   which is correctness of the carded check, not scope creep. The
   parent chain the parser already keeps made it three lines.
4. Empty alt="" is flagged with the intentional-decorative caveat in
   evidence per the card — surfaced, priced by the cost mapping, not
   silently passed and not harshly failed.
5. Contrast honesty implemented as specified: fg/bg resolved from
   self-or-ancestor INLINE styles only (mirroring inheritance the
   snippet actually carries); class/external-CSS/translucent-rgba
   colors resolve to None and the element is reported "not statically
   checkable — NOT counted as passing". The all-unchecked case skips
   with the count in the reason.
6. WCAG math per the 2.1 spec: per-channel sRGB gamma expansion with
   the spec's 0.03928 knee, Rec. 709 weighting, (L1+0.05)/(L2+0.05);
   held exact by tests (black-on-white 21.0, white-on-white 1.0,
   symmetric).
7. Scope creep declined, per the timebox: heading structure, ARIA
   validity, focus order, large-text contrast tiers and the rest of
   WCAG 2.1 AA went to docs/inclusive-roadmap.md's "does NOT cover" and
   reopening-conditions sections, not into today's code.

Gate evidence (July 29, 2026): full suite 184 passed (21 new G-6
tests), ruff clean, mypy clean. The documented example gates the
generated HTML email end-to-end — verdict ABSTAIN, decided per-check,
with alt_text_presence naming the hero <img> without alt (score 0.500,
confidence 1.000); the inline-styled paragraph passes contrast at
12.6:1; the class-styled promo line is surfaced as not statically
checkable; label_association skips (no form controls). Fixtures cover
each check firing, each skip reason, the empty-alt caveat, the
malformed-HTML tolerance path, ABSTAIN-grade registration through a
normal cost_map entry, and both axe degradation messages.
