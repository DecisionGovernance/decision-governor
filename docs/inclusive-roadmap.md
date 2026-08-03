# Inclusive deployment gate — roadmap

v0.1 is the **commenced minimal inclusive gate, not a Section 508
conformance claim.** That sentence is the whole contract of this page:
what ships today is honest about its boundary, and everything beyond the
boundary is listed here with a version, not implied by silence.

## What v0.1 covers

Three static, deterministic checks (`decision_governor.inclusive`),
registerable through the standard Check protocol and priceable through
the normal cost mapping like any other check:

| Check | What it verifies | WCAG anchor |
|---|---|---|
| `alt_text_presence` | every `<img>` carries non-empty alt text; a present-but-empty `alt=""` is flagged with an explicit may-be-intentional-decorative caveat rather than silently passed or harshly failed | 1.1.1 |
| `contrast_arithmetic` | WCAG contrast ratio ≥ 4.5:1 (AA, normal text) — computed **only** where both foreground and background colors are statically extractable from inline styles; everything else is reported as *not statically checkable*, never counted as passing | 1.4.3 |
| `label_association` | every labelable form control has an accessible label via `label[for]`, `aria-label`, `aria-labelledby`, or a wrapping `<label>` | 1.3.1 / 4.1.2 |

All three parse with the standard library's `html.parser` (no `bs4`,
keeping the base install's no-heavy-deps promise), are tolerant of the
imperfect HTML LLMs actually generate, and skip with a stated reason on
non-HTML output rather than guessing.

## What v0.1 does NOT cover

Stated plainly, because an unstated gap reads as a covered one:

- **Dynamic rendering** — anything requiring a browser or DOM execution:
  computed styles, CSS cascade from external stylesheets or classes,
  media queries, JavaScript-injected content.
- **Assistive-technology compatibility** — no screen-reader or AT
  behavior is exercised or simulated.
- **The full WCAG 2.1 AA ruleset** — dozens of success criteria are not
  checked, including (not limited to) heading structure, link purpose,
  language attributes, table semantics, and text alternatives beyond
  images.
- **ARIA state and property correctness** — roles, states, and
  `aria-*` value validity.
- **Focus order and keyboard navigation** — tab sequence, focus
  visibility, keyboard traps.
- **Large-text and non-text contrast tiers** — v0.1 applies the single
  4.5:1 normal-text threshold; the 3:1 large-text and UI-component
  thresholds are not distinguished.

The `contrast_arithmetic` evidence line "not statically checkable" is
this section expressed at runtime: an element whose colors come from a
class or an external stylesheet is reported as unknown, because
reporting unknown as safe would be false safety.

## Reopening conditions

- **v0.2 — axe-core adapter.** The shell ships in v0.1
  (`inclusive/axe.py`): it detects Node.js and skips cleanly with a
  stated reason. v0.2 completes the subprocess runner (pipe HTML to
  axe-core, parse JSON results into `CheckResult`), bringing the
  industry-standard ruleset in as one more deterministic check. This
  descope was pre-authorized on the G-6 card and is recorded in
  docs/G6-checklist.md.
- **v0.2+ — full ruleset growth.** Additional native checks (heading
  structure, ARIA validity, large-text contrast tiers) ride behind the
  axe adapter, which covers most of them wholesale; native
  reimplementation happens only where the no-Node degraded path needs
  it.

## The worked example

`examples/inclusive_html_gate.py` gates a generated HTML email template
with one `<img>` missing its alt attribute: the gate returns ABSTAIN
with the missing alt named in the reasons, the adequate-contrast
paragraph passes arithmetically, and the class-styled paragraph is
surfaced as not statically checkable. That documented example is the
G-6 gate criterion, end to end.
