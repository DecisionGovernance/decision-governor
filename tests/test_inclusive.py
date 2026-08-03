"""Card G-6 gate: the documented example gates a generated HTML snippet.

Fixtures per the gate run: a clean HTML doc (all skip-or-pass), docs
with a missing alt / low contrast / unlabeled input (each check fires
with correct evidence), the "not statically checkable" path (contrast on
a class-styled element skips with the honest reason), the WCAG contrast
math held exact, ABSTAIN-grade registration through a normal cost_map
entry, the axe shell's clean degradation, and the worked example run
end-to-end.
"""
from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from decision_governor import Decision, Governor
from decision_governor.inclusive import (
    AltTextPresence,
    AxeCoreCheck,
    ContrastArithmetic,
    LabelAssociation,
    contrast_ratio,
    parse_css_color,
    relative_luminance,
)
from decision_governor.inclusive._html import looks_like_html, parse_elements
from decision_governor.risk import CostStructure, CVaRPolicy

CLEAN_HTML = """\
<html><body style="background-color: #ffffff">
  <img src="logo.png" alt="Acme logo">
  <p style="color: #333333">Your order has shipped.</p>
  <form><label for="em">Email</label><input id="em" type="email"></form>
</body></html>
"""


# ------------------------------------------------------- the parsing seam


def test_parser_is_tolerant_of_malformed_html():
    # Unclosed tags, a stray end tag, a valueless attribute: no exception,
    # elements still collected — leniency is the design, not an accident.
    elements = parse_elements("<div><p>text</span><img src='x.png' alt>")
    tags = [e.tag for e in elements]
    assert tags == ["div", "p", "img"]
    assert elements[2].attrs["alt"] == ""  # valueless attr normalizes to ""


def test_looks_like_html_requires_a_known_tag():
    assert looks_like_html("<p>hello</p>")
    assert not looks_like_html("plain prose, 2 < 3 and x > 1")
    assert not looks_like_html('{"json": "<notatag>"}')


def test_parent_chain_and_text_accumulation():
    elements = parse_elements("<div style='color: red'><p>inner text</p></div>")
    p = next(e for e in elements if e.tag == "p")
    assert p.text.strip() == "inner text"
    assert p.parent is not None and p.parent.tag == "div"


# ------------------------------------------------------ alt_text_presence


def test_alt_missing_fires_with_evidence():
    html = '<body><img src="hero.png"><img src="logo.png" alt="Logo"></body>'
    result = AltTextPresence().run(html, {})
    assert result.score == pytest.approx(0.5)
    assert result.confidence == 1.0
    assert len(result.evidence) == 1 and "hero.png" in result.evidence[0]


def test_alt_empty_is_flagged_with_the_decorative_caveat():
    result = AltTextPresence().run('<body><img src="spacer.gif" alt=""></body>', {})
    assert result.score == 1.0
    assert "intentional-decorative" in result.evidence[0]


def test_alt_skips_on_non_html_and_on_no_images():
    no_html = AltTextPresence().run("A plain text summary.", {})
    assert no_html.score == 0.0 and "n/a: output is not HTML" in no_html.evidence[0]
    no_imgs = AltTextPresence().run("<p>no images here</p>", {})
    assert no_imgs.score == 0.0 and "n/a: no images" in no_imgs.evidence[0]


def test_alt_clean_doc_passes():
    result = AltTextPresence().run(CLEAN_HTML, {})
    assert result.score == 0.0 and result.evidence == []


# --------------------------------------------------- contrast_arithmetic


def test_wcag_contrast_math_is_exact():
    black, white = (0, 0, 0), (255, 255, 255)
    assert relative_luminance(black) == 0.0
    assert relative_luminance(white) == pytest.approx(1.0)
    assert contrast_ratio(black, white) == pytest.approx(21.0)   # the spec's maximum
    assert contrast_ratio(white, white) == pytest.approx(1.0)    # and its minimum
    assert contrast_ratio(white, black) == contrast_ratio(black, white)  # symmetric


def test_parse_css_color_forms_and_honest_nones():
    assert parse_css_color("#fff") == (255, 255, 255)
    assert parse_css_color("#336699") == (0x33, 0x66, 0x99)
    assert parse_css_color("rgb(255, 0, 0)") == (255, 0, 0)
    assert parse_css_color("RGBA(0, 0, 0, 1)") == (0, 0, 0)
    assert parse_css_color("navy") == (0, 0, 128)
    # Not statically resolvable -> None, never a guess.
    assert parse_css_color("rgba(0, 0, 0, 0.5)") is None   # translucent
    assert parse_css_color("var(--brand)") is None
    assert parse_css_color("cornflowerblue") is None       # beyond the shipped table
    assert parse_css_color("rgb(300, 0, 0)") is None


def test_low_contrast_fires_below_aa():
    html = '<p style="color: #999999; background-color: #ffffff">fine print</p>'
    result = ContrastArithmetic().run(html, {})
    assert result.score == 1.0
    assert any("< 4.5:1 AA" in line for line in result.evidence)


def test_contrast_inherits_background_from_ancestors():
    html = ('<body style="background-color: #ffffff">'
            '<p style="color: #333333">body text</p></body>')
    result = ContrastArithmetic().run(html, {})
    assert result.score == 0.0  # 12.6:1 via the inherited body background
    assert any("worst ratio 12.6:1" in line for line in result.evidence)


def test_class_styled_element_is_not_statically_checkable():
    html = '<p class="promo">Reply STOP to unsubscribe.</p>'
    result = ContrastArithmetic().run(html, {})
    assert result.score == 0.0
    assert "not statically checkable" in result.evidence[0]  # skip, honest reason


def test_translucent_inline_background_is_not_statically_checkable():
    # An explicit rgba(...) with alpha < 1 composites with the backdrop, so
    # the effective background is not static. It must make the element
    # unchecked — NOT be skipped in favor of an opaque ancestor background,
    # which would report a contrast the page never renders.
    html = ('<body style="background-color: #ffffff">'
            '<p style="color: #767676; background-color: rgba(0, 0, 0, 0.5)">'
            'overlay text</p></body>')
    result = ContrastArithmetic().run(html, {})
    assert result.score == 0.0
    assert "not statically checkable" in result.evidence[0]  # skip, not a false pass
    assert not any("worst ratio" in line for line in result.evidence)


def test_explicit_unresolvable_color_declaration_stops_the_ancestor_walk():
    # Same principle on the foreground side: `color: var(--x)` overrides any
    # inherited color, so the walk must not substitute an ancestor's value.
    html = ('<body style="color: #000000; background-color: #ffffff">'
            '<p style="color: var(--brand)">brand text</p></body>')
    result = ContrastArithmetic().run(html, {})
    assert "not statically checkable" in result.evidence[0]


def test_mixed_doc_notes_unchecked_elements_alongside_checked_ones():
    html = ('<body style="background-color: #ffffff">'
            '<p style="color: #333333">checked</p>'
            '<p class="promo">not checkable</p></body>')
    result = ContrastArithmetic().run(html, {})
    assert result.score == 0.0
    assert any("NOT counted as passing" in line for line in result.evidence)


# ---------------------------------------------------- label_association


def test_every_recognized_label_mechanism_passes():
    html = """
    <form>
      <label for="a">A</label><input id="a" type="text">
      <input type="search" aria-label="Search the site">
      <span id="q3">C</span><input type="text" aria-labelledby="q3">
      <label>Wrapped <input type="text" name="wrapped"></label>
    </form>
    """
    result = LabelAssociation().run(html, {})
    assert result.score == 0.0 and result.evidence == []


def test_aria_labelledby_target_with_nested_markup_counts_as_labeled():
    # The parser stores text on the innermost open element, so the <span>'s
    # own .text is empty here — the resolver must gather descendant text or
    # this valid label ("Visible label") false-fails the gate.
    html = ('<form><span id="lbl"><b>Visible label</b></span>'
            '<input type="text" name="n" aria-labelledby="lbl"></form>')
    result = LabelAssociation().run(html, {})
    assert result.score == 0.0 and result.evidence == []


def test_aria_labelledby_with_missing_target_is_unlabeled():
    # A dangling IDREF gives assistive tech no name at all: the attribute
    # being present must not count as a label when nothing resolves.
    html = '<form><input type="text" name="q" aria-labelledby="missing"></form>'
    result = LabelAssociation().run(html, {})
    assert result.score == 1.0
    assert "name=q" in result.evidence[0]


def test_aria_labelledby_requires_every_idref_to_resolve():
    # One valid target plus one dangling reference is still a broken name
    # computation — every listed IDREF must exist.
    html = ('<form><span id="q3">C</span>'
            '<input type="text" name="partial" aria-labelledby="q3 missing"></form>')
    result = LabelAssociation().run(html, {})
    assert result.score == 1.0


def test_aria_labelledby_with_empty_target_text_is_unlabeled():
    html = ('<form><span id="empty"></span>'
            '<input type="text" name="e" aria-labelledby="empty"></form>')
    result = LabelAssociation().run(html, {})
    assert result.score == 1.0


def test_unlabeled_input_fires_with_identifying_evidence():
    html = '<form><input type="text" name="q"><input type="submit"></form>'
    result = LabelAssociation().run(html, {})
    assert result.score == 1.0  # submit is excluded; the one labelable control fails
    assert "name=q" in result.evidence[0]


def test_only_excluded_types_means_skip_not_pass():
    html = '<form><input type="hidden" name="csrf"><input type="submit"></form>'
    result = LabelAssociation().run(html, {})
    assert "n/a: no labelable form controls" in result.evidence[0]


# ----------------------------------------------------------- axe shell


def test_axe_degrades_cleanly_without_node(monkeypatch):
    import decision_governor.inclusive.axe as axe_module

    monkeypatch.setattr(axe_module.shutil, "which", lambda _: None)
    check = AxeCoreCheck()
    result = check.run("<p>anything</p>", {})
    assert result.score == 0.0
    assert "requires Node.js" in result.evidence[0]
    assert check.describe()["config"]["node_detected"] is False


def test_axe_is_a_stated_stub_even_with_node(monkeypatch):
    import decision_governor.inclusive.axe as axe_module

    monkeypatch.setattr(axe_module.shutil, "which", lambda _: "/usr/bin/node")
    result = AxeCoreCheck().run("<p>anything</p>", {})
    assert result.score == 0.0
    assert "v0.2" in result.evidence[0]  # the descope is stated, not silent


# ------------------------------------------- ABSTAIN grade via cost_map


def _inclusive_gate() -> Governor:
    checks = (AltTextPresence(), ContrastArithmetic(), LabelAssociation())
    gov = Governor(
        policy=CVaRPolicy(
            alpha=0.05,
            costs=CostStructure(accessibility_violation=250.0, abstention=4.0),
            cost_map={check.name: "accessibility_violation" for check in checks},
        ),
        deployment="inclusive-gate-test",
    )
    for check in checks:
        gov.register(check)
    return gov


def test_checks_register_at_abstain_grade_via_normal_cost_mapping():
    verdict = _inclusive_gate().evaluate('<body><img src="hero.png"></body>')
    assert verdict.decision is Decision.ABSTAIN
    assert any("alt_text_presence" in reason for reason in verdict.reasons)


def test_clean_html_is_allowed_through_the_same_gate():
    verdict = _inclusive_gate().evaluate(CLEAN_HTML)
    assert verdict.decision is Decision.ALLOW


# --------------------------------------------- the gate run (documented)


def test_the_documented_example_gates_the_snippet_end_to_end(capsys):
    example = Path(__file__).resolve().parents[1] / "examples" / "inclusive_html_gate.py"
    module = runpy.run_path(str(example))
    verdict = module["main"]()
    assert verdict.decision is Decision.ABSTAIN
    assert any(
        "alt_text_presence" in reason and "hero-summer" in reason
        for reason in verdict.reasons
    )
    out = capsys.readouterr().out
    assert "decision: abstain" in out and "email held" in out
