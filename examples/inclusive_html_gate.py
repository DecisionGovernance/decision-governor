"""
examples/inclusive_html_gate.py
============================================================
Decision Governor — The Inclusive Deployment Gate (Card G-6)
============================================================

This is the G-6 gate example: a generated HTML email template
is gated by the three v0.1 inclusive checks before it ships.
The template below has one <img> missing its alt attribute —
a real accessibility violation on user-facing HTML — and the
gate returns ABSTAIN with the missing alt named in the
reasons: a genuine stop, not a warning.

Three ideas to notice while reading:

1.  Accessibility violations are priced like any other error.
    The cost mapping routes all three checks to one named
    cost, `accessibility_violation`, priced meaningfully
    against a cheap abstention — so a confident violation on
    user-facing HTML resolves to ABSTAIN through the same
    CVaR arithmetic as every other check in the SDK.

2.  The contrast check is honest about coverage. The inline-
    styled paragraph is checked arithmetically (12.6:1,
    passes); the class-styled promo line is surfaced as "not
    statically checkable" — unknown is reported as unknown,
    never as safe.

3.  v0.1 is the commenced minimal gate, NOT a Section 508
    conformance claim. What full validation adds, and when,
    is docs/inclusive-roadmap.md.

Run:  python examples/inclusive_html_gate.py
Requires only the base install (no API keys, no bs4, no Node).
"""

from decision_governor import Decision, Governor
from decision_governor.core.results import Verdict
from decision_governor.inclusive import (
    AltTextPresence,
    ContrastArithmetic,
    LabelAssociation,
)
from decision_governor.risk import CostStructure, CVaRPolicy

# ------------------------------------------------------------
# 1. The generated output being governed: an HTML email with
#    one <img> missing alt (the hero), one correctly-labeled
#    logo, an inline-styled body (checkable contrast), and a
#    class-styled promo line (NOT statically checkable).
# ------------------------------------------------------------

EMAIL_HTML = """\
<html>
  <body style="background-color: #ffffff">
    <img src="https://cdn.example.com/hero-summer.png" width="600">
    <img src="https://cdn.example.com/logo.png" alt="Acme Outfitters logo">
    <p style="color: #333333">
      Your summer order has shipped and should arrive within three days.
    </p>
    <p class="promo-fineprint">
      Reply STOP to unsubscribe from promotional email.
    </p>
  </body>
</html>
"""

# ------------------------------------------------------------
# 2. Costs in the deployment's own units, and the gate
# ------------------------------------------------------------

costs = CostStructure(
    accessibility_violation=250.0,  # exclusion + legal exposure per shipped violation
    abstention=4.0,                 # holding the email for a human fix is cheap
)

CHECKS = (AltTextPresence(), ContrastArithmetic(), LabelAssociation())


def build_inclusive_gate() -> Governor:
    gov = Governor(
        policy=CVaRPolicy(
            alpha=0.05,
            costs=costs,
            # Normal cost mapping — the checks are ordinary checks; the
            # ABSTAIN grade comes from the pricing, not a special flag.
            cost_map={check.name: "accessibility_violation" for check in CHECKS},
        ),
        deployment="inclusive-html-gate-example",
    )
    for check in CHECKS:
        gov.register(check)
    return gov


# ------------------------------------------------------------
# 3. The gate run
# ------------------------------------------------------------

def main() -> Verdict:
    gov = build_inclusive_gate()
    verdict = gov.evaluate(EMAIL_HTML, context={"gate": "outbound_email"})

    print(f"decision: {verdict.decision.value}")
    for reason in verdict.reasons:
        print(f"  - {reason}")

    if verdict.decision is not Decision.ALLOW:
        print("email held: fix the flagged markup and re-gate")
    return verdict


if __name__ == "__main__":
    main()
    # Expected: ABSTAIN. The alt_text_presence reason names the hero
    # <img> without alt (1 of 2 images -> score 0.500, confidence 1.000);
    # contrast_arithmetic reports the checked paragraph's ratio and the
    # promo line as not statically checkable; label_association skips
    # (no form controls in an email).
