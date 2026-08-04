"""Card G-7 gate: integrations behind extras, and the agent example's
four fates.

Fixtures per the card: the base package imports in an environment with
every optional dependency BLOCKED (the extras discipline is a test, not
a promise); the middleware hands out request-scoped governors whose
records carry the correlation id; the health route exposes structure and
never record contents; the judge is structurally confined (deterministic
not settable, floating aliases refused, temperature 0, defensive
parsing, full prompt + raw response in evidence); and the agent example
prints its four fates and round-trips through audit export/verify.
"""
from __future__ import annotations

import importlib.util
import json
import runpy
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from decision_governor import Decision, Governor
from decision_governor.instrumentation.schema import validate_record
from decision_governor.instrumentation.sinks import SQLiteSink
from decision_governor.integrations.fastapi import HEALTH_PATH, GovernorMiddleware
from decision_governor.integrations.llm_judge import (
    DEGRADED_CONFIDENCE,
    DEGRADED_SCORE,
    AnthropicProvider,
    LLMJudgeCheck,
    OpenAICompatibleProvider,
    is_floating_alias,
    parse_constrained,
)
from decision_governor.risk import CostStructure, CVaRPolicy

REPO_ROOT = Path(__file__).resolve().parent.parent

# ------------------------------------------------- Step 0: extras discipline


def test_base_package_imports_with_every_optional_dependency_blocked(tmp_path):
    # The card's rule made executable: a user who never installs the
    # extras must never hit an ImportError from importing the package —
    # including the integrations modules themselves.
    script = tmp_path / "base_import_probe.py"
    script.write_text(textwrap.dedent("""\
        import sys

        BLOCKED = {
            "fastapi", "starlette", "pydantic", "openai", "anthropic",
            "huggingface_hub", "sentence_transformers", "transformers",
        }

        class BlockOptionalDeps:
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ModuleNotFoundError(f"blocked optional dependency: {name}")
                return None

        sys.meta_path.insert(0, BlockOptionalDeps())
        for name in list(sys.modules):
            if name.split(".")[0] in BLOCKED:
                del sys.modules[name]

        import decision_governor
        import decision_governor.integrations
        import decision_governor.integrations.fastapi
        import decision_governor.integrations.llm_judge
        print("BASE-IMPORT-OK")
    """))
    probe = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=False
    )
    assert probe.returncode == 0, probe.stderr
    assert "BASE-IMPORT-OK" in probe.stdout


# ------------------------------------------------- Step 1: the FastAPI seam


class _FakeApp:
    """Duck-typed FastAPI stand-in: records health-route registration."""

    def __init__(self):
        self.routes: list[tuple[str, object, list[str]]] = []

    def add_api_route(self, path, endpoint, methods):
        self.routes.append((path, endpoint, methods))


def _request(headers=None):
    return SimpleNamespace(headers=headers or {})


def _factory_with(sink):
    def factory() -> Governor:
        gov = Governor(
            policy=CVaRPolicy(
                alpha=0.05,
                costs=CostStructure(err=100.0, abstention=3.0),
                default_cost="err",
            ),
            log=sink,
            deployment="factory-default",
        )
        gov.register(_CleanCheck())
        return gov

    return factory


class _CleanCheck:
    name = "clean_check"
    deterministic = True
    seen_context: dict | None = None

    def run(self, output, context):
        from decision_governor.core.types import CheckResult

        type(self).seen_context = dict(context)
        return CheckResult(score=0.0, confidence=1.0, evidence=[])


def test_each_request_gets_a_fresh_governor_and_correlation_id():
    mw = GovernorMiddleware(_FakeApp(), _factory_with(SQLiteSink()), deployment="svc")
    a = mw.get_governor(_request())
    b = mw.get_governor(_request())
    assert a is not b  # factory, not instance: no cross-request leakage
    assert a.correlation_id != b.correlation_id
    assert a.deployment == b.deployment == "svc"


def test_correlation_header_tags_the_stored_record():
    sink = SQLiteSink()
    mw = GovernorMiddleware(_FakeApp(), _factory_with(sink), deployment="svc")
    gov = mw.get_governor(_request({"x-correlation-id": "req-123"}))
    verdict = gov.evaluate("clean output", context={"gate": "summarize"})

    record = sink.read(verdict.record_id)
    assert record["correlation_id"] == "req-123"
    assert record["deployment"] == "svc"
    assert validate_record(record) == []  # the extra key rides schema v1.0

    # The bound context carried the ids into the evaluation itself, so
    # the context digest covers them too.
    assert _CleanCheck.seen_context["correlation_id"] == "req-123"
    assert _CleanCheck.seen_context["deployment"] == "svc"
    assert _CleanCheck.seen_context["gate"] == "summarize"  # caller keys win


def test_report_outcome_flows_through_the_correlated_sink():
    sink = SQLiteSink()
    mw = GovernorMiddleware(_FakeApp(), _factory_with(sink), deployment="svc")
    gov = mw.get_governor(_request({"x-correlation-id": "req-9"}))
    verdict = gov.evaluate("ok", context={"gate": "g"})
    gov.report_outcome(verdict.record_id, ok=True, detail={"latency_ms": 12})
    record = sink.read(verdict.record_id)
    assert record["execution_outcome"]["reported"] is True
    assert record["correlation_id"] == "req-9"


def test_health_exposes_structure_and_never_record_contents():
    sink = SQLiteSink()
    mw = GovernorMiddleware(_FakeApp(), _factory_with(sink), deployment="svc")
    gov = mw.get_governor(_request())
    gov.evaluate("SECRET-PAYLOAD-MARKER", context={"gate": "g"})

    payload = mw.health()
    assert payload == {
        "deployment": "svc",
        "checks": ["clean_check"],
        "policy": "CVaRPolicy",
        "sink": "ok",
    }
    assert "SECRET-PAYLOAD-MARKER" not in json.dumps(payload)


def test_health_reports_an_absent_sink():
    def factory() -> Governor:
        gov = Governor(deployment="no-log")
        gov.register(_CleanCheck())
        return gov

    mw = GovernorMiddleware(_FakeApp(), factory, deployment="svc")
    assert mw.health()["sink"] == "none"


def test_health_route_is_registered_and_optional():
    app = _FakeApp()
    mw = GovernorMiddleware(app, _factory_with(SQLiteSink()), deployment="svc")
    assert app.routes == [(HEALTH_PATH, mw.health, ["GET"])]

    bare = _FakeApp()
    GovernorMiddleware(bare, _factory_with(SQLiteSink()), deployment="svc",
                       health_route=False)
    assert bare.routes == []


def test_depends_pattern_end_to_end_with_real_fastapi(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    from decision_governor.instrumentation.sinks import JsonlSink

    # Jsonl, not SQLite: TestClient serves the endpoint on a worker
    # thread, and sqlite3 connections are thread-bound.
    sink = JsonlSink(tmp_path / "web_records.jsonl")
    app = FastAPI()
    mw = GovernorMiddleware(app, _factory_with(sink), deployment="web-svc")

    @app.post("/summarize")
    def summarize(gov: Governor = Depends(mw.get_governor)) -> dict:
        verdict = gov.evaluate("a clean summary", context={"gate": "summarize"})
        return {
            "decision": verdict.decision.value,
            "record_id": verdict.record_id,
            "correlation_id": gov.correlation_id,
        }

    client = TestClient(app)
    response = client.post("/summarize", headers={"x-correlation-id": "trace-7"})
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "allow"
    assert body["correlation_id"] == "trace-7"
    assert sink.read(body["record_id"])["correlation_id"] == "trace-7"

    health = client.get(HEALTH_PATH)
    assert health.status_code == 200
    assert health.json()["policy"] == "CVaRPolicy"


# --------------------------------------------- Steps 2-3: the LLM judge


class _FakeProvider:
    def __init__(self, response="", error=None):
        self.response = response
        self.error = error
        self.calls: list[tuple[str, str, float]] = []

    def complete(self, prompt, model, temperature):
        self.calls.append((prompt, model, temperature))
        if self.error is not None:
            raise self.error
        return self.response


PINNED = "claude-3-5-sonnet-20241022"
TEMPLATE = "Judge this output for policy violations: {output}"


@pytest.mark.parametrize("alias", [
    "latest", "gpt-4", "gpt-4o", "claude-3-5-sonnet", "llama3",
    "claude-sonnet-latest", "gpt-4o:latest", "", None,
])
def test_floating_aliases_are_floating(alias):
    assert is_floating_alias(alias)


@pytest.mark.parametrize("pinned", [
    PINNED, "gpt-4o-2024-08-06", "o3-2025-04-16",
    "llama3.1@sha256:0123456789abcdef",
])
def test_pinned_versions_are_not_floating(pinned):
    assert not is_floating_alias(pinned)


def test_constructor_refuses_floating_aliases_hard():
    with pytest.raises(ValueError, match="pinned, dated"):
        LLMJudgeCheck("judge", _FakeProvider(), "gpt-4", TEMPLATE)


def test_deterministic_is_hardcoded_and_unassignable():
    judge = LLMJudgeCheck("judge", _FakeProvider(), PINNED, TEMPLATE)
    assert judge.deterministic is False
    with pytest.raises(AttributeError):
        judge.deterministic = True  # no caller can promote the judge
    with pytest.raises(TypeError):
        LLMJudgeCheck("judge", _FakeProvider(), PINNED, TEMPLATE,
                      deterministic=True)  # not a constructor parameter


def test_run_uses_temperature_zero_and_logs_full_prompt_and_response():
    raw = '{"score": 0.8, "confidence": 0.9, "reason": "tone contradicts policy"}'
    provider = _FakeProvider(response=raw)
    judge = LLMJudgeCheck("judge", provider, PINNED, TEMPLATE)

    result = judge.run("the output under judgment", {})
    prompt, model, temperature = provider.calls[0]
    assert temperature == 0.0  # always — a varying judge is unauditable
    assert model == PINNED
    assert result.score == pytest.approx(0.8)
    assert result.confidence == pytest.approx(0.9)
    # FULL prompt + raw response: the judge's reasoning is auditable.
    assert prompt in result.evidence[1]
    assert raw in result.evidence[2]
    assert "tone contradicts policy" in result.evidence


def test_fenced_and_wrapped_json_still_parses():
    fenced = 'Sure! Here is my judgment:\n```json\n{"score": 0.2, "confidence": 1.0, "reason": "minor"}\n```'
    parsed = parse_constrained(fenced)
    assert parsed is not None and parsed.score == pytest.approx(0.2)
    clamped = parse_constrained('{"score": 7, "confidence": -2, "reason": "x"}')
    assert clamped is not None
    assert clamped.score == 1.0 and clamped.confidence == 0.0


def test_malformed_judge_output_degrades_conservatively_never_crashes():
    judge = LLMJudgeCheck("judge", _FakeProvider(response="It looks fine to me!"),
                          PINNED, TEMPLATE)
    result = judge.run("output", {})
    assert result.score == DEGRADED_SCORE
    assert result.confidence == DEGRADED_CONFIDENCE
    assert any("malformed judge output" in line for line in result.evidence)


def test_malformed_template_rendering_degrades_conservatively_never_crashes():
    # A placeholder the context doesn't carry is a natural authoring
    # mistake; it must reach the documented degradation path, not raise
    # KeyError before a verdict exists.
    provider = _FakeProvider(response='{"score": 0, "confidence": 1, "reason": "x"}')
    judge = LLMJudgeCheck("judge", provider, PINNED,
                          "Judge {output} against {missing_context_field}")
    result = judge.run("output", {})
    assert result.score == DEGRADED_SCORE
    assert result.confidence == DEGRADED_CONFIDENCE
    assert any("template rendering failed" in line for line in result.evidence)
    assert provider.calls == []  # the provider was never reached


def test_literal_json_example_in_template_degrades_not_crashes():
    # Unescaped braces in a literal JSON example — the other natural
    # authoring mistake str.format punishes.
    judge = LLMJudgeCheck("judge", _FakeProvider(), PINNED,
                          'Judge {output}. Respond as {"score": 0.5}')
    result = judge.run("output", {})
    assert result.score == DEGRADED_SCORE
    assert any("template rendering failed" in line for line in result.evidence)


def test_provider_failure_degrades_conservatively_never_crashes():
    judge = LLMJudgeCheck("judge", _FakeProvider(error=RuntimeError("api down")),
                          PINNED, TEMPLATE)
    result = judge.run("output", {})
    assert result.score == DEGRADED_SCORE
    assert result.confidence == DEGRADED_CONFIDENCE
    assert any("provider call failed" in line for line in result.evidence)


def test_a_clean_judge_verdict_cannot_authorize_allow():
    # The structural point of deterministic=False: with only the judge
    # registered, ALLOW is unreachable — absence of deterministic proof
    # is not permission, ceiling SCALE.
    judge = LLMJudgeCheck(
        "judge", _FakeProvider(response='{"score": 0, "confidence": 1, "reason": "clean"}'),
        PINNED, TEMPLATE,
    )
    gov = Governor(
        policy=CVaRPolicy(alpha=0.05, costs=CostStructure(err=100.0, abstention=3.0),
                          default_cost="err"),
    )
    gov.register(judge)
    verdict = gov.evaluate("anything")
    assert verdict.decision is Decision.SCALE
    assert verdict.decided_by == "ceiling"


def test_describe_carries_the_pin_into_audit_bundles():
    judge = LLMJudgeCheck("judge", _FakeProvider(), PINNED, TEMPLATE)
    config = judge.describe()["config"]
    assert config["model"] == PINNED
    assert config["provider"] == "_FakeProvider"
    assert config["temperature"] == 0.0
    assert len(config["prompt_template_sha256"]) == 64


def test_openai_compatible_provider_calls_the_injected_client():
    created = {}

    class FakeChatCompletions:
        def create(self, **kwargs):
            created.update(kwargs)
            message = SimpleNamespace(content='{"score": 0.1}')
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeChatCompletions()))
    provider = OpenAICompatibleProvider(base_url="http://localhost:11434/v1", client=client)
    raw = provider.complete("the prompt", PINNED, temperature=0.0)
    assert raw == '{"score": 0.1}'
    assert created["model"] == PINNED
    assert created["temperature"] == 0.0
    assert created["messages"] == [{"role": "user", "content": "the prompt"}]


def test_anthropic_provider_calls_the_injected_client():
    created = {}

    class FakeMessages:
        def create(self, **kwargs):
            created.update(kwargs)
            return SimpleNamespace(content=[SimpleNamespace(text="{}"), SimpleNamespace(text="!")])

    provider = AnthropicProvider(client=SimpleNamespace(messages=FakeMessages()))
    raw = provider.complete("p", PINNED, temperature=0.0)
    assert raw == "{}!"
    assert created["max_tokens"] == 1024
    assert created["temperature"] == 0.0


@pytest.mark.skipif(
    importlib.util.find_spec("openai") is not None,
    reason="openai installed; the missing-SDK path does not apply",
)
def test_missing_sdk_raises_the_install_hint_not_a_bare_import_error():
    provider = OpenAICompatibleProvider()
    with pytest.raises(ModuleNotFoundError, match=r"decision-governor\[llm\]"):
        provider.complete("p", PINNED, temperature=0.0)


# ------------------------------------------ Step 4: the agent example


def test_agent_example_prints_its_four_fates_and_round_trips_the_bundle(tmp_path):
    # Gate clause: the four fates in stdout — the regression guard that
    # the frozen `output: Any` contract still lets non-text decisions
    # (ToolCall objects) flow through.
    example = REPO_ROOT / "examples" / "agent_tool_gate.py"
    run = subprocess.run(
        [sys.executable, str(example)],
        capture_output=True, text=True, check=False, cwd=tmp_path,
    )
    assert run.returncode == 0, run.stderr
    assert "[executed] send_email" in run.stdout                    # ALLOW
    assert "[scaled -> manager_approval_queue]" in run.stdout       # SCALE
    assert "[abstained] send_email" in run.stdout                   # ABSTAIN
    assert "[scaled -> soft_delete_with_review]" in run.stdout      # SCALE

    # And the example's closing claim, held true: the decisions it just
    # made export to a bundle that verifies.
    from decision_governor.instrumentation.audit import export, verify

    bundle = export(SQLiteSink(tmp_path / "agent_decisions.db"), tmp_path / "bundle")
    result = verify(bundle)
    assert result.passed, result.report


def test_agent_example_turns_malformed_tool_args_into_verdicts(tmp_path, monkeypatch):
    # Mapping[str, Any] permits garbage args; the gate must record and
    # route the proposed action, not crash before a verdict exists.
    monkeypatch.chdir(tmp_path)  # the example logs to agent_decisions.db in cwd
    module = runpy.run_path(str(REPO_ROOT / "examples" / "agent_tool_gate.py"))
    tool_call = module["ToolCall"]
    governed_execute = module["governed_execute"]

    scaled = governed_execute(
        tool_call("issue_refund", {"amount": "not-a-number"}, provenance="user_prompt")
    )
    assert scaled.startswith("[scaled -> manager_approval_queue]")
    assert "malformed amount 'not-a-number'" in scaled

    abstained = governed_execute(
        tool_call("send_email", {"to": None}, provenance="user_prompt")
    )
    assert abstained.startswith("[abstained]")
    assert "malformed recipient None" in abstained
