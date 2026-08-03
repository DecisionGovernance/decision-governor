"""The shared HTML parsing seam — Step 1 of Card G-6 (everything depends on it).

One stdlib parser feeds all three inclusive checks — no bs4, keeping the
base install's "no heavy deps" promise. `html.parser` is deliberately
lenient: it won't choke on the imperfect HTML that LLMs actually
generate, which is the point. If an element can't be parsed, the checks
that depend on it skip with a stated reason rather than crashing.

Elements keep a parent link so checks can walk ancestors (inline-style
inheritance for contrast, wrapping <label> for association) without a
second parse.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

# Void elements never take children; they must not be pushed as parents.
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
})

# Tag names that make text "look like HTML" — a tag-shaped token alone is
# not enough (XML, code snippets, "<3"), so the name must be a known one.
_HTML_TAGS = frozenset({
    "html", "head", "body", "title", "meta", "link", "style", "script",
    "div", "span", "p", "a", "img", "br", "hr", "strong", "em", "b", "i",
    "u", "small", "sup", "sub", "blockquote", "pre", "code",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
    "form", "input", "label", "select", "option", "textarea", "button",
    "fieldset", "legend",
    "section", "article", "header", "footer", "nav", "main", "aside",
    "figure", "figcaption",
})

_TAG_TOKEN = re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)")


@dataclass
class Element:
    """One start/startend tag: tag name, attributes, approximate source
    line, accumulated direct text content, and a parent link."""

    tag: str
    attrs: dict[str, str]
    source_line: int
    parent: Element | None = None
    text: str = ""

    def style(self) -> dict[str, str]:
        """The inline style attribute as a {property: value} dict
        (lower-cased property names, whitespace-stripped values)."""
        out: dict[str, str] = {}
        for declaration in self.attrs.get("style", "").split(";"):
            prop, sep, value = declaration.partition(":")
            if sep:
                out[prop.strip().lower()] = value.strip()
        return out


class _ElementCollector(HTMLParser):
    """Collects every start/startend tag as an Element, maintaining a
    parent stack and accumulating each element's direct text content.
    Tolerant by construction: HTMLParser does not raise on bad markup,
    and a stray end tag simply pops to the nearest matching open tag."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[Element] = []
        self._stack: list[Element] = []

    def _record(self, tag: str, attrs: list[tuple[str, str | None]], push: bool) -> None:
        element = Element(
            tag=tag.lower(),
            # Valueless attributes (e.g. bare `alt`) normalize to "".
            attrs={k.lower(): (v if v is not None else "") for k, v in attrs},
            source_line=self.getpos()[0],
            parent=self._stack[-1] if self._stack else None,
        )
        self.elements.append(element)
        if push and element.tag not in _VOID_TAGS:
            self._stack.append(element)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(tag, attrs, push=True)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._record(tag, attrs, push=False)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i].tag == tag.lower():
                del self._stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self._stack and data.strip():
            self._stack[-1].text += data


def parse_elements(html: str) -> list[Element]:
    """Parse once, feed all three checks: a flat, document-order list of
    Element(tag, attrs, text, source_line, parent)."""
    collector = _ElementCollector()
    collector.feed(html)
    collector.close()
    return collector.elements


def looks_like_html(text: str) -> bool:
    """Does this output plausibly contain HTML worth checking? Requires a
    tag-shaped token whose name is a known HTML tag, so plain prose,
    JSON, and arbitrary XML skip rather than being force-parsed."""
    return any(
        match.group(1).lower() in _HTML_TAGS
        for match in _TAG_TOKEN.finditer(text)
    )
