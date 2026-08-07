"""Docs equal code: the README's own code blocks, executed.

The quickstart is the first thing a stranger runs. These tests execute the
block *extracted from README.md itself*, so the file can never drift from
the library: change one without the other and this fails.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from decision_governor import Governor, GateResult, gate
from decision_governor.core.types import CheckResult, Decision

README = Path(__file__).resolve().parent.parent / "README.md"

_PYTHON_BLOCK = re.compile(r"^```python\n(.*?)^```", re.DOTALL | re.MULTILINE)


def _quickstart_blocks() -> list[str]:
    """The python blocks in the Quickstart section, in document order."""
    text = README.read_text(encoding="utf-8")
    start = text.index("## Quickstart")
    end = text.index("## Why this exists", start)
    return _PYTHON_BLOCK.findall(text[start:end])


def test_readme_has_the_two_quickstart_blocks():
    # Guards the extraction itself: if the section is restructured, the
    # tests below must be re-pointed rather than silently passing on
    # whatever block happens to be first.
    assert len(_quickstart_blocks()) == 2


def test_quickstart_runs_verbatim_on_a_base_install(tmp_path, monkeypatch):
    """Part 1 must run as printed, with no model extras installed.

    It writes decisions.db to the working directory, so run it in tmp_path.
    """
    block = _quickstart_blocks()[0]
    assert "ClaimsSupported" not in block, (
        "the base-install quickstart must not use a check that needs the "
        "[llm] extra; model-backed checks belong in Part 2"
    )

    monkeypatch.chdir(tmp_path)
    namespace: dict[str, object] = {"__name__": "__readme__"}
    exec(compile(block, "README.md::quickstart", "exec"), namespace)

    result = namespace["result"]
    assert isinstance(result, GateResult)
    # Clean text through a deterministic check: ALLOW is reachable, and the
    # printed branch in the README is the one a reader actually sees.
    assert result.decision is Decision.ALLOW
    assert result.reasons == []
    assert (tmp_path / "decisions.db").exists()


def test_quickstart_part_two_block_is_valid_python():
    """Part 2 needs the [llm] extra to run, but must never be malformed."""
    block = _quickstart_blocks()[1]
    compile(block, "README.md::quickstart-part-2", "exec")


def test_facts_receives_the_wrapped_calls_kwargs():
    """The contract Part 2 documents: `facts` is handed kwargs, not the
    evaluation context. Naming its parameter `ctx` once led readers to
    index it as the full context; this locks the real shape."""
    seen: dict[str, object] = {}

    class Recorder:
        name = "recorder"
        deterministic = True

        def run(self, output, context):
            seen.update(context)
            return CheckResult(score=0.0, confidence=1.0)

    gov = Governor()
    gov.register(Recorder())

    @gate(gov, checks=["recorder"], facts=lambda kwargs: kwargs["source_document"])
    def summarize(llm, source_document: str) -> str:
        return f"Summary: {source_document}"

    result = summarize(object(), source_document="ground truth")

    assert result.decision is Decision.ALLOW
    assert seen["gate"] == "summarize"
    assert seen["kwargs"] == {"source_document": "ground truth"}
    assert seen["facts"] == "ground truth"


def test_fact_source_passed_positionally_is_not_visible_to_facts():
    """The flip side of that contract, stated so it stays intentional:
    positional arguments never reach `facts`. The README passes the fact
    source by keyword for exactly this reason."""
    gov = Governor()

    class Clean:
        name = "clean"
        deterministic = True

        def run(self, output, context):
            return CheckResult(score=0.0, confidence=1.0)

    gov.register(Clean())

    @gate(gov, checks=["clean"], facts=lambda kwargs: kwargs["source_document"])
    def summarize(source_document: str) -> str:
        return f"Summary: {source_document}"

    with pytest.raises(KeyError):
        summarize("passed positionally")
