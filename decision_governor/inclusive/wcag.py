"""Card G-6 — the three native inclusive checks (Steps 2–4, timeboxed).

The v0.1 boundary, stated where the code lives: three static,
deterministic checks — alt-text presence, contrast arithmetic on
statically-extractable inline colors, and form-label association. This
is the COMMENCED minimal inclusive gate, not a Section 508 or WCAG 2.1
AA conformance claim; what full validation adds (and when) is
docs/inclusive-roadmap.md's job, not another check's.

The load-bearing design decision is honesty about coverage: colors set
via external CSS, classes, or inheritance often are NOT statically
extractable from the HTML snippet alone, and contrast_arithmetic says so
explicitly rather than pretending those elements passed — the same
refuse-to-pretend principle as the modality guard, applied to contrast.

All three are deterministic with confidence 1.0: presence/absence and
arithmetic are facts, not judgments — these checks *know*.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from decision_governor.checks._base import CheckBase, clamp01, extract_text
from decision_governor.core.types import CheckResult
from decision_governor.inclusive._html import Element, looks_like_html, parse_elements

# WCAG 2.1 SC 1.4.3 (contrast minimum), normal text.
AA_NORMAL_TEXT_RATIO = 4.5

# ------------------------------------------------------------- color math
# The 16 basic CSS colors plus the aliases LLM-generated email HTML
# actually uses. An unknown name is None — not statically checkable —
# never a guess.
_NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0), "white": (255, 255, 255), "silver": (192, 192, 192),
    "gray": (128, 128, 128), "grey": (128, 128, 128), "maroon": (128, 0, 0),
    "red": (255, 0, 0), "purple": (128, 0, 128), "fuchsia": (255, 0, 255),
    "magenta": (255, 0, 255), "green": (0, 128, 0), "lime": (0, 255, 0),
    "olive": (128, 128, 0), "yellow": (255, 255, 0), "navy": (0, 0, 128),
    "blue": (0, 0, 255), "teal": (0, 128, 128), "aqua": (0, 255, 255),
    "cyan": (0, 255, 255), "orange": (255, 165, 0),
}
_HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_RGB = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(?:,\s*([\d.]+)\s*)?\)$"
)


def parse_css_color(value: str) -> tuple[int, int, int] | None:
    """#rgb / #rrggbb / rgb() / opaque rgba() / basic named colors.
    Anything else (var(), gradients, translucent rgba, unknown names)
    returns None: not statically resolvable, so not checkable — honesty
    over a guessed default."""
    value = value.strip().lower()
    if value in _NAMED_COLORS:
        return _NAMED_COLORS[value]
    hex_match = _HEX.match(value)
    if hex_match:
        digits = hex_match.group(1)
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    rgb_match = _RGB.match(value)
    if rgb_match:
        r, g, b = (int(rgb_match.group(i)) for i in (1, 2, 3))
        if max(r, g, b) > 255:
            return None
        alpha = rgb_match.group(4)
        if alpha is not None and float(alpha) < 1.0:
            return None  # translucent over an unknown backdrop: not static
        return (r, g, b)
    return None


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.1 relative luminance: per-channel sRGB gamma expansion
    (the spec's 0.03928 knee), then the Rec. 709 weighting."""
    def channel(v: int) -> float:
        c = v / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    """(L_lighter + 0.05) / (L_darker + 0.05); black on white is 21.0."""
    lighter, darker = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _inline_color(element: Element, *properties: str) -> tuple[int, int, int] | None:
    """Nearest self-or-ancestor inline value for any of `properties`.
    Walking ancestors mirrors CSS inheritance for `color` and backdrop
    stacking for `background` — but an EXPLICIT declaration is
    authoritative: if the nearest one doesn't parse (translucent rgba,
    var(), gradient), the effective value is not static, and the walk
    stops with None rather than inheriting an ancestor value the
    declaration would in fact override or composite with."""
    node: Element | None = element
    while node is not None:
        style = node.style()
        for prop in properties:
            value = style.get(prop)
            if value is None:
                continue
            color = parse_css_color(value)
            if color is None and prop == "background":
                # Shorthand: the first token may be the color layer.
                tokens = value.split()
                color = parse_css_color(tokens[0]) if tokens else None
            return color
        node = node.parent
    return None


def _text_content(root: Element, elements: list[Element]) -> str:
    """Text of `root` AND its descendants. The shared parser stores data
    only on the innermost open element, so a label like
    <span id="x"><b>Visible</b></span> keeps its text on the <b>, not the
    <span> — the descendants must be gathered via parent links or nested
    markup would read as empty."""
    parts = [root.text]
    for element in elements:
        node = element.parent
        while node is not None:
            if node is root:
                parts.append(element.text)
                break
            node = node.parent
    return " ".join(parts)


def _truncate(value: str, limit: int = 60) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


# ------------------------------------------------------ the three checks


class AltTextPresence(CheckBase):
    """Every <img> needs non-empty alt text (WCAG 1.1.1).

    A present-but-EMPTY alt (`alt=""`) is an intentional signal for
    decorative images in the WCAG spec, so the honest v0.1 choice is to
    flag it with that caveat in the evidence — not silently pass it, not
    harshly fail it; surface it and let the cost mapping decide severity.
    """

    name = "alt_text_presence"
    deterministic = True

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult:
        text = extract_text(output)
        if not looks_like_html(text):
            return self.skip("output is not HTML")
        imgs = [e for e in parse_elements(text) if e.tag == "img"]
        if not imgs:
            return self.skip("no images in output")

        evidence: list[str] = []
        failing = 0
        for img in imgs:
            alt = img.attrs.get("alt")
            if alt is not None and alt.strip():
                continue
            failing += 1
            src = _truncate(img.attrs.get("src", "?"))
            if alt is None:
                evidence.append(f"<img> without alt at ~line {img.source_line}, src={src}")
            else:
                evidence.append(
                    f'<img> with empty alt="" at ~line {img.source_line}, src={src} '
                    "(empty alt may be intentional-decorative; flagged, not silently passed)"
                )
        return CheckResult(
            score=clamp01(failing / len(imgs)), confidence=1.0, evidence=evidence
        )


class ContrastArithmetic(CheckBase):
    """WCAG AA contrast (4.5:1, normal text) — but ONLY where both
    foreground and background are statically extractable from inline
    styles. Elements styled via classes, external CSS, or inheritance the
    snippet doesn't carry are reported as "not statically checkable",
    never counted as passing: an unchecked element is unknown, and
    reporting unknown as safe would be false safety."""

    name = "contrast_arithmetic"
    deterministic = True

    def _config(self) -> dict[str, Any]:
        return {"aa_normal_text_ratio": AA_NORMAL_TEXT_RATIO}

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult:
        text = extract_text(output)
        if not looks_like_html(text):
            return self.skip("output is not HTML")
        bearing = [
            e for e in parse_elements(text)
            if e.text.strip() and e.tag not in ("script", "style", "title")
        ]
        if not bearing:
            return self.skip("no text-bearing elements in output")

        checkable: list[tuple[Element, float]] = []
        unchecked = 0
        for element in bearing:
            fg = _inline_color(element, "color")
            bg = _inline_color(element, "background-color", "background")
            if fg is None or bg is None:
                unchecked += 1
                continue
            checkable.append((element, contrast_ratio(fg, bg)))

        if not checkable:
            return self.skip(
                "no element had both colors statically extractable "
                f"({unchecked} not statically checkable — colors from CSS classes, "
                "external stylesheets, or inheritance the snippet doesn't carry)"
            )

        failing = [(e, r) for e, r in checkable if r < AA_NORMAL_TEXT_RATIO]
        evidence = [
            f"contrast {ratio:.1f}:1 (< {AA_NORMAL_TEXT_RATIO}:1 AA) on <{e.tag}> "
            f"at ~line {e.source_line}: {_truncate(e.text.strip(), 40)!r}"
            for e, ratio in failing
        ]
        worst = min(ratio for _, ratio in checkable)
        evidence.append(f"checked {len(checkable)} element(s); worst ratio {worst:.1f}:1")
        if unchecked:
            evidence.append(
                f"note: {unchecked} element(s) not statically checkable (colors from "
                "CSS classes or inheritance) — NOT counted as passing"
            )
        return CheckResult(
            score=1.0 if failing else 0.0, confidence=1.0, evidence=evidence
        )


class LabelAssociation(CheckBase):
    """Every labelable form control needs an accessible label (WCAG
    1.3.1 / 4.1.2) via one of the recognized association mechanisms:
    label[for], aria-label, aria-labelledby, or a wrapping <label> —
    checking all of them avoids false failures on validly-labeled
    inputs. aria-labelledby is RESOLVED, not taken on faith: every
    space-separated IDREF must name a parsed element and the referenced
    text content (descendants included) must be non-empty, because a
    dangling reference gives assistive tech no name at all. hidden/submit/button inputs are excluded: they
    don't need labels, and including them would generate false
    positives."""

    name = "label_association"
    deterministic = True

    _EXCLUDED_TYPES = ("hidden", "submit", "button")

    def _config(self) -> dict[str, Any]:
        return {"excluded_input_types": list(self._EXCLUDED_TYPES)}

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult:
        text = extract_text(output)
        if not looks_like_html(text):
            return self.skip("output is not HTML")
        elements = parse_elements(text)
        controls = [
            e for e in elements
            if e.tag in ("input", "select", "textarea")
            and e.attrs.get("type", "").lower() not in self._EXCLUDED_TYPES
        ]
        if not controls:
            return self.skip("no labelable form controls in output")

        labels_for = {
            label.attrs.get("for") for label in elements if label.tag == "label"
        } - {None, ""}
        by_id: dict[str, Element] = {}
        for e in elements:
            element_id = e.attrs.get("id")
            if element_id and element_id not in by_id:
                by_id[element_id] = e

        def labelledby_resolves(control: Element) -> bool:
            refs = control.attrs.get("aria-labelledby", "").split()
            if not refs:
                return False
            targets = [by_id.get(ref) for ref in refs]
            if any(t is None for t in targets):
                return False  # a dangling IDREF contributes no name
            return any(
                _text_content(t, elements).strip() for t in targets if t is not None
            )

        def labeled(control: Element) -> bool:
            if control.attrs.get("id") in labels_for:
                return True
            if control.attrs.get("aria-label", "").strip():
                return True
            if labelledby_resolves(control):
                return True
            node = control.parent  # wrapping <label> is the implicit form
            while node is not None:
                if node.tag == "label":
                    return True
                node = node.parent
            return False

        unlabeled = [e for e in controls if not labeled(e)]
        evidence = [
            f"<{e.tag}> without accessible label at ~line {e.source_line} "
            f"(id={e.attrs.get('id', 'none')}, name={e.attrs.get('name', 'none')})"
            for e in unlabeled
        ]
        return CheckResult(
            score=clamp01(len(unlabeled) / len(controls)),
            confidence=1.0,
            evidence=evidence,
        )
