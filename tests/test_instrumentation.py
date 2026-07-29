"""G-4 gate: the cryptographic round-trip.

Canonical-bytes property tests, the record builder and the sentinel
assertion, the decided_by tri-state fixtures, sinks, outcomes, the
export -> verify round trip with ZERO mismatches, the non-negotiable
mutation test, CLI exit codes, monitors, and the hand-computed
actuarial fixtures.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from decision_governor import (
    CheckResult,
    Decision,
    Governor,
    NoLogConfigured,
)
from decision_governor.instrumentation import (
    BUNDLE_HASH_RECIPE,
    CallbackSink,
    JsonlSink,
    LogWriteError,
    SQLiteSink,
    TelegramSink,
    UnknownRecord,
    build_record,
    canonical_bytes,
    digest_of,
    digestible_view,
    export,
    ibnr_ultimate,
    resolve_sink,
    sha256_hex,
    snapshot,
    time_to_outcome,
    validate_record,
    verify,
)
from decision_governor.core.policy import ThresholdPolicy
from decision_governor.instrumentation.cli import main as cli_main
from decision_governor.risk import CostStructure, CVaRPolicy


class FixedCheck:
    def __init__(self, name, deterministic, score, confidence=1.0):
        self.name = name
        self.deterministic = deterministic
        self._result = CheckResult(score=score, confidence=confidence)

    def run(self, output, context):
        return self._result

    def describe(self):
        return {"name": self.name, "deterministic": self.deterministic,
                "class": "FixedCheck", "config": {}}


# ------------------------------------------------------ canonical bytes


json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-(10**9), max_value=10**9)
    | st.floats(allow_nan=False, allow_infinity=False, width=64)
    | st.text(max_size=20),
    lambda children: st.lists(children, max_size=4)
    | st.dictionaries(st.text(max_size=8), children, max_size=4),
    max_leaves=20,
)


@settings(max_examples=200)
@given(value=json_values)
def test_canonical_bytes_is_deterministic_under_copies_and_key_order(value):
    assert canonical_bytes(value) == canonical_bytes(copy.deepcopy(value))
    if isinstance(value, dict):
        shuffled = dict(reversed(list(value.items())))
        assert canonical_bytes(value) == canonical_bytes(shuffled)


def test_canonical_bytes_forbids_nan_and_non_json():
    with pytest.raises(ValueError):
        canonical_bytes({"x": float("nan")})
    with pytest.raises(TypeError):
        canonical_bytes({"x": object()})


def test_digestible_view_policy():
    class Payload:
        def __init__(self):
            self.secret = "SENTINEL-NEVER-LOGGED"

        def digest(self):
            return "abc123"

    view = digestible_view(
        {"plain": "text", "n": 3, "payload": Payload(), "blob": b"bytes"}
    )
    serialized = canonical_bytes(view).decode()
    assert "SENTINEL-NEVER-LOGGED" not in serialized
    assert '"digest":"abc123"' in serialized
    assert "<unserializable: bytes>" in serialized


# ----------------------------------------- record builder and decided_by


def _cvar_governor(log=None, abstention=3.0):
    costs = CostStructure(err=100.0, abstention=abstention)
    policy = CVaRPolicy(alpha=0.05, costs=costs, default_cost="err")
    gov = Governor(policy=policy, log=log, deployment="test-deploy")
    gov.register(FixedCheck("det_a", True, 0.001))
    gov.register(FixedCheck("det_b", True, 0.001))
    gov.register(FixedCheck("learned", False, 0.0))
    return gov


def test_build_record_shape_and_sentinel_absence():
    gov = _cvar_governor()
    context = {"gate": "application", "facts": ["fact one"], "note": "ctx"}
    verdict = gov.evaluate("output", context)
    record = build_record(verdict, gov.policy, context, "test-deploy")
    assert validate_record(record) == []
    assert record["gate"] == "application"
    assert record["decision"] == verdict.decision.value
    # The context itself never enters the record — digest only.
    serialized = canonical_bytes(record).decode()
    assert "fact one" not in serialized
    assert record["context_digest"] == digest_of(
        digestible_view({"gate": "application", "facts": ["fact one"], "note": "ctx"})
    )


def test_decided_by_aggregate_fixture():
    verdict = _cvar_governor().evaluate("out", {}, checks=["det_a", "det_b"])
    assert verdict.decision is Decision.SCALE
    assert verdict.decided_by == "aggregate"


def test_decided_by_ceiling_fixture():
    verdict = _cvar_governor().evaluate("out", {}, checks=["learned"])
    assert verdict.decision is Decision.SCALE
    assert verdict.decided_by == "ceiling"  # no-det cap, most structural


def test_decided_by_per_check_fixture():
    # Deontic bar fires per-check (cvar 60 > 50) so the per-check verdict
    # is SCALE, while the gate's economic argmin would pick ALLOW (60 <
    # scale 63 < abstain 90): composition, not aggregate, decides.
    costs = CostStructure(err=100.0, abstention=90.0)
    policy = CVaRPolicy(alpha=0.05, costs=costs, default_cost="err")
    gov = Governor(policy=policy)
    gov.register(FixedCheck("hot", True, 0.03))
    verdict = gov.evaluate("out")
    assert verdict.decision is Decision.SCALE
    assert verdict.decided_by == "per_check"


def test_decided_by_allow_is_per_check():
    gov = _cvar_governor()
    verdict = gov.evaluate("out", {}, checks=["det_a"])
    assert verdict.decision is Decision.ALLOW
    assert verdict.decided_by == "per_check"


# ----------------------------------------------------------------- sinks


def _record_stub(record_id, ts, gate="g"):
    return {"record_id": record_id, "recorded_at": ts, "gate": gate, "x": 1}


@pytest.mark.parametrize("make", [
    lambda p: SQLiteSink(p / "log.db"),
    lambda p: JsonlSink(p / "log.jsonl"),
])
def test_sinks_write_read_query(tmp_path, make):
    sink = make(tmp_path)
    sink.write(_record_stub("a", "2026-07-28T01:00:00"))
    sink.write(_record_stub("b", "2026-07-28T02:00:00", gate="other"))
    assert sink.read("a")["record_id"] == "a"
    with pytest.raises(UnknownRecord, match="same sink"):
        sink.read("missing")
    assert [r["record_id"] for r in sink.query()] == ["a", "b"]
    assert [r["record_id"] for r in sink.query(gate="other")] == ["b"]
    assert [r["record_id"] for r in sink.query(from_ts="2026-07-28T01:30:00")] == ["b"]
    # Re-write is last-write-wins in both sinks.
    sink.write({**_record_stub("a", "2026-07-28T01:00:00"), "x": 2})
    assert sink.read("a")["x"] == 2
    assert len(list(sink.query())) == 2


def test_resolve_sink_accepts_sink_path_none(tmp_path):
    assert resolve_sink(None) is None
    assert isinstance(resolve_sink(str(tmp_path / "d.db")), SQLiteSink)
    jsonl = JsonlSink(tmp_path / "d.jsonl")
    assert resolve_sink(jsonl) is jsonl
    with pytest.raises(TypeError, match="log must be"):
        resolve_sink(42)


def test_log_write_failure_is_loud_but_not_lossy():
    class BrokenSink:
        def write(self, record):
            raise OSError("disk full")

        def read(self, record_id):
            raise UnknownRecord(record_id)

        def query(self, from_ts=None, to_ts=None, gate=None):
            return iter(())

    gov = _cvar_governor(log=BrokenSink())
    with pytest.raises(LogWriteError, match="disk full") as excinfo:
        gov.evaluate("out", {}, checks=["det_a"])
    # The verdict rides on the error: the decision is not lost.
    assert excinfo.value.verdict.decision is Decision.ALLOW


def test_governor_logs_and_reports_outcomes(tmp_path):
    gov = _cvar_governor(log=str(tmp_path / "decisions.db"))
    verdict = gov.evaluate("out", {"gate": "apply"}, checks=["det_a", "det_b"])
    stored = gov.log.read(verdict.record_id)
    assert stored["decision"] == "scale"
    assert stored["execution_outcome"] == {"reported": False, "revision": 0}

    gov.report_outcome(verdict.record_id, ok=True, detail={"user_edit_distance": 4})
    first = gov.log.read(verdict.record_id)["execution_outcome"]
    assert first["reported"] is True and first["ok"] is True
    assert first["revision"] == 1 and first["detail"] == {"user_edit_distance": 4}
    # Idempotent last-write-wins; revision counts the writes.
    gov.report_outcome(verdict.record_id, ok=False)
    second = gov.log.read(verdict.record_id)["execution_outcome"]
    assert second["ok"] is False and second["revision"] == 2

    with pytest.raises(UnknownRecord):
        gov.report_outcome("no-such-record", ok=True)
    with pytest.raises(NoLogConfigured, match="log="):
        _cvar_governor().report_outcome("x", ok=True)


# --------------------------------------------- export / verify round trip


@pytest.fixture()
def cvar_bundle(tmp_path):
    """A real multi-record run: one record per decided_by value reachable
    under one config, one reported outcome, one model-backed check."""
    gov = _cvar_governor(log=str(tmp_path / "decisions.db"))
    r_aggregate = gov.evaluate("out", {"gate": "apply"}, checks=["det_a", "det_b"])
    r_ceiling = gov.evaluate("out", {"gate": "apply"}, checks=["learned"])
    r_full = gov.evaluate("out", {"gate": "apply"})  # includes model-backed
    gov.report_outcome(r_aggregate.record_id, ok=True)
    assert (r_aggregate.decided_by, r_ceiling.decided_by) == ("aggregate", "ceiling")
    out = export(gov.log, tmp_path / "bundle")
    return out, (r_aggregate, r_ceiling, r_full)


def test_export_verify_round_trip_zero_mismatches(cvar_bundle):
    bundle, _ = cvar_bundle
    result = verify(bundle)
    assert result.passed, result.report
    assert result.record_count == 3
    assert result.recomputed == 3
    assert result.mismatches == []
    assert "0 mismatches" in result.report
    assert "model-backed" in result.report  # the models are not in the bundle
    assert "PASS" in result.report


def test_per_check_decided_by_round_trips_with_threshold_policy(tmp_path):
    gov = Governor(log=str(tmp_path / "t.db"))
    gov.register(FixedCheck("strict", True, 0.7))
    verdict = gov.evaluate("out", {"gate": "g"})
    assert verdict.decided_by == "per_check"
    bundle = export(gov.log, tmp_path / "bundle-threshold")
    result = verify(bundle)
    assert result.passed, result.report


def test_bundle_hash_recipe_is_independently_recomputable(cvar_bundle):
    bundle, _ = cvar_bundle
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["bundle_hash_recipe"] == BUNDLE_HASH_RECIPE
    # An independent implementer, from the recipe alone:
    recomputed = sha256_hex(canonical_bytes(manifest["files"]))
    assert recomputed == manifest["bundle_sha256"]


def _remanifest(bundle: Path) -> None:
    """Recompute the manifest as an adversary who CAN hash but cannot
    fake the decision math."""
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    files = {
        name: sha256_hex((bundle / name).read_bytes())
        for name in manifest["files"]
    }
    manifest["files"] = files
    manifest["bundle_sha256"] = sha256_hex(canonical_bytes(files))
    (bundle / "manifest.json").write_bytes(canonical_bytes(manifest))


def test_mutation_is_caught_and_named(cvar_bundle, tmp_path):
    bundle, (r_aggregate, _, _) = cvar_bundle
    tampered = tmp_path / "tampered"
    tampered.mkdir()
    for path in bundle.iterdir():
        (tampered / path.name).write_bytes(path.read_bytes())

    lines = (tampered / "records.jsonl").read_text(encoding="utf-8").splitlines()
    flipped = []
    for line in lines:
        record = json.loads(line)
        if record["record_id"] == r_aggregate.record_id:
            record["decision"] = "allow"  # the tamper: SCALE -> ALLOW
        flipped.append(canonical_bytes(record).decode())
    (tampered / "records.jsonl").write_text("\n".join(flipped) + "\n", encoding="utf-8")

    # Without re-manifesting, the hash pass catches it.
    hash_result = verify(tampered)
    assert not hash_result.passed
    assert any("hash mismatch" in p for p in hash_result.problems)

    # With hashes regenerated, the recompute pass catches it — naming
    # the record. This is the non-negotiable mutation test.
    _remanifest(tampered)
    result = verify(tampered)
    assert not result.passed
    assert any(m["record_id"] == r_aggregate.record_id for m in result.mismatches)
    assert "decision" in result.mismatches[0]["fields"]
    assert "FAIL" in result.report


def test_redacted_costs_skip_economic_recompute(cvar_bundle, tmp_path):
    _, _ = cvar_bundle
    gov = _cvar_governor(log=str(tmp_path / "r.db"))
    gov.evaluate("out", {"gate": "apply"}, checks=["det_a"])
    bundle = export(gov.log, tmp_path / "redacted", redact_costs=True)
    config = json.loads((bundle / "config.json").read_text(encoding="utf-8"))
    assert config["costs"] == {"err": None, "abstention": None}  # names stay
    result = verify(bundle)
    assert result.passed, result.report
    assert any("costs redacted" in note for note in result.notes)


def test_schema_validation_flags_malformed_records():
    assert validate_record({}) != []
    problems = validate_record(
        {"schema_version": "1.0", "record_id": "x", "decision": "maybe"}
    )
    assert any("'maybe'" in p for p in problems)


# ------------------------------------------------------------------- CLI


def test_cli_export_and_verify_exit_codes(tmp_path, capsys):
    gov = _cvar_governor(log=str(tmp_path / "cli.db"))
    gov.evaluate("out", {"gate": "apply"}, checks=["det_a", "det_b"])
    bundle_dir = str(tmp_path / "cli-bundle")
    assert cli_main(["audit", "export", "--db", str(tmp_path / "cli.db"),
                     "-o", bundle_dir]) == 0
    assert cli_main(["audit", "verify", bundle_dir]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out

    # Tamper (with re-manifest) -> exit 1.
    bundle = Path(bundle_dir)
    lines = (bundle / "records.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["decision"] = "allow"
    (bundle / "records.jsonl").write_text(
        canonical_bytes(record).decode() + "\n", encoding="utf-8"
    )
    _remanifest(bundle)
    assert cli_main(["audit", "verify", bundle_dir]) == 1


# -------------------------------------------------------------- monitors


def test_monitor_snapshot_and_notifiers(tmp_path):
    gov = _cvar_governor(log=str(tmp_path / "m.db"))
    for _ in range(3):
        gov.evaluate("out", {"gate": "apply"}, checks=["det_a"])       # allow
    scale = gov.evaluate("out", {"gate": "apply"}, checks=["det_a", "det_b"])
    gov.evaluate("out", {"gate": "other"}, checks=["learned"])          # scale
    gov.report_outcome(scale.record_id, ok=True)

    report = snapshot(gov.log.query())
    assert report.total == 5
    assert report.allow_rate == pytest.approx(3 / 5)
    assert report.scale_rate == pytest.approx(2 / 5)
    assert report.outcome_reported_fraction == pytest.approx(1 / 5)
    assert "apply" in report.gate_rates and "other" in report.gate_rates
    assert 0.0 <= report.gate_rates["apply"]["Z"] <= 1.0
    assert any("decisions" in line for line in report.lines)

    callback = CallbackSink()
    for line in report.lines:
        callback.notify(line)
    assert callback.messages == report.lines

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        TelegramSink(chat_id="1", token=None) if not __import__("os").environ.get(
            "TELEGRAM_BOT_TOKEN"
        ) else (_ for _ in ()).throw(ValueError("TELEGRAM_BOT_TOKEN"))


def test_telegram_notify_degrades_on_network_failure(monkeypatch):
    """A send failure must not abort the monitoring run: notify() warns
    and returns False instead of propagating the network error."""
    import urllib.error

    def boom(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    sink = TelegramSink(chat_id="42", token="tok-123")
    with pytest.warns(UserWarning, match="TelegramSink.notify failed"):
        assert sink.notify("hello") is False


def test_monitor_snapshot_empty_and_trend():
    assert snapshot([]).total == 0
    calm = [{"decision": "allow", "checks": [], "gate": "g",
             "execution_outcome": {"reported": False}}] * 4
    worried = [{"decision": "abstain", "checks": [], "gate": "g",
                "execution_outcome": {"reported": False}}] * 4
    assert snapshot(calm + worried).abstention_trend_flag is True
    assert snapshot(calm + calm).abstention_trend_flag is False


def test_canonical_view_edges_and_schema_branches(monkeypatch, tmp_path):
    # Non-finite floats become declared placeholders, never poison.
    view = digestible_view({"bad": float("nan"), "worse": float("inf")})
    assert view["bad"].startswith("<non-finite") and view["worse"].startswith("<non-finite")

    class Slotted:
        __slots__ = ()

    assert digestible_view(Slotted()) == "<unserializable: Slotted>"

    # Schema: malformed check entries are named.
    record_problems = validate_record(
        {"schema_version": "1.0", "checks": ["not-a-dict", {"name": 1}]}
    )
    assert any("checks[0] is not an object" in p for p in record_problems)
    assert any("checks[1].name is not of type string" in p for p in record_problems)

    # Sinks: upper-bound filter.
    sink = JsonlSink(tmp_path / "t.jsonl")
    sink.write(_record_stub("a", "2026-07-28T01:00:00"))
    sink.write(_record_stub("b", "2026-07-28T09:00:00"))
    assert [r["record_id"] for r in sink.query(to_ts="2026-07-28T05:00:00")] == ["a"]

    # Verify degrades loudly on broken bundles.
    empty = tmp_path / "not-a-bundle"
    empty.mkdir()
    result = verify(empty)
    assert not result.passed and "not an audit bundle" in result.problems[0]

    # TelegramSink pulls the env token when not passed explicitly.
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok-123")
    assert TelegramSink(chat_id="42").token == "tok-123"


def test_verify_rejects_manifest_that_omits_required_member(cvar_bundle):
    """An adversary who CAN hash cannot shrink the bundle: dropping a
    required member from the manifest, re-sealing the bundle hash, and
    leaving the now-unverified file in place must still FAIL."""
    bundle, _ = cvar_bundle
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"].pop("pins.json")  # model provenance, dropped from the seal
    manifest["bundle_sha256"] = sha256_hex(canonical_bytes(manifest["files"]))
    (bundle / "manifest.json").write_bytes(canonical_bytes(manifest))
    assert (bundle / "pins.json").exists()  # the unverified file is still present

    result = verify(bundle)
    assert not result.passed
    assert any(
        "pins.json" in p and "not listed" in p for p in result.problems
    ), result.report


def test_verify_spans_a_threshold_policy_change(tmp_path):
    """Two valid decisions with identical evidence but different policies
    in one log: each must verify against the policy it was decided under,
    not against the first record's thresholds."""
    sink = SQLiteSink(tmp_path / "spanning.db")
    decisions = []
    for scale_at in (0.25, 0.8):
        gov = Governor(
            policy=ThresholdPolicy(scale_at=scale_at, abstain_at=0.9), log=sink
        )
        gov.register(FixedCheck("check", True, 0.3))
        decisions.append(gov.evaluate("out", {"gate": "g"}).decision.value)
    assert decisions == ["scale", "allow"]  # same evidence, different policy

    result = verify(export(sink, tmp_path / "spanning-bundle"))
    assert result.passed, result.report
    assert result.record_count == 2
    assert result.recomputed == 2
    assert result.mismatches == []


def test_verify_fails_structurally_on_schema_invalid_record(cvar_bundle):
    """A correctly hashed but schema-invalid bundle must return the
    promised structured FAIL, not crash in recomputation."""
    bundle, _ = cvar_bundle
    (bundle / "records.jsonl").write_bytes(b"{}\n")  # valid JSON, invalid schema
    _remanifest(bundle)  # adversary re-seals the hashes

    result = verify(bundle)  # must not raise KeyError
    assert not result.passed
    assert any("record" in p for p in result.problems), result.report
    assert "FAIL" in result.report


def test_cli_verify_exit_1_on_schema_invalid_record(tmp_path):
    gov = _cvar_governor(log=str(tmp_path / "s.db"))
    gov.evaluate("out", {"gate": "apply"}, checks=["det_a"])
    bundle_dir = str(tmp_path / "s-bundle")
    export(gov.log, Path(bundle_dir))
    bundle = Path(bundle_dir)
    (bundle / "records.jsonl").write_bytes(b"{}\n")
    _remanifest(bundle)
    assert cli_main(["audit", "verify", bundle_dir]) == 1


@pytest.mark.parametrize("payload, needle", [
    (b"[]\n", "not a JSON object"),           # valid JSON, wrong shape
    (b"{not-json}\n", "invalid JSON"),        # syntactically broken stream
])
def test_verify_fails_structurally_on_malformed_records_stream(
    cvar_bundle, payload, needle
):
    """A correctly hashed but malformed records.jsonl — non-object JSON or
    a broken stream — must return a structured FAIL, not a traceback."""
    bundle, _ = cvar_bundle
    (bundle / "records.jsonl").write_bytes(payload)
    _remanifest(bundle)

    result = verify(bundle)  # must not raise
    assert not result.passed
    assert any(needle in p for p in result.problems), result.report
    assert "FAIL" in result.report


@pytest.mark.parametrize("name, payload, needle", [
    ("manifest.json", b"[]", "manifest.json is not a JSON object"),
    ("config.json", b"{bad-json}", "config.json is not valid JSON"),
    ("config.json", b"[]", "config.json is not a JSON object"),
    ("pins.json", b"{bad-json}", "pins.json is not valid JSON"),
])
def test_verify_fails_structurally_on_malformed_bundle_inputs(
    cvar_bundle, name, payload, needle
):
    """manifest.json/config.json/pins.json that are invalid JSON or the
    wrong shape must return a structured FAIL, not a traceback."""
    bundle, _ = cvar_bundle
    (bundle / name).write_bytes(payload)
    if name != "manifest.json":
        # config/pins are hashed by the manifest, so re-seal to reach the
        # shape check; the manifest itself is parsed before any hashing.
        _remanifest(bundle)

    result = verify(bundle)  # must not raise
    assert not result.passed
    assert any(needle in p for p in result.problems), result.report
    assert "FAIL" in result.report


@pytest.mark.parametrize("payload", [b"{}", b"[]"])
def test_verify_flags_pins_detached_from_records(cvar_bundle, payload):
    """pins.json is reconciled against the records' check descriptions;
    an emptied or wrong-shaped summary fails, and the report's pins line
    is derived from the records rather than trusting the summary."""
    bundle, _ = cvar_bundle
    (bundle / "pins.json").write_bytes(payload)
    _remanifest(bundle)

    result = verify(bundle)
    assert not result.passed
    assert any("pins.json" in p for p in result.problems), result.report
    # Derived from records, so the model-backed checks still surface.
    assert "pins:" in result.report
    assert "learned" in result.report


def test_verify_catches_dropped_record_via_manifest_count(tmp_path):
    """Truncating records.jsonl and re-sealing its hash still leaves the
    sealed manifest record_count as a tripwire — even when the dropped
    record reuses checks that pin reconciliation would accept."""
    sink = SQLiteSink(tmp_path / "trunc.db")
    gov = Governor(policy=ThresholdPolicy(), log=sink)
    gov.register(FixedCheck("check", True, 0.3))
    gov.evaluate("out", {"gate": "g"})
    gov.evaluate("out", {"gate": "g"})  # a second, identical-shaped decision
    bundle = export(sink, tmp_path / "trunc-bundle")

    lines = (bundle / "records.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    (bundle / "records.jsonl").write_text(lines[0] + "\n", encoding="utf-8")
    _remanifest(bundle)  # regenerate file + bundle hashes, leave count at 2

    result = verify(bundle)
    assert not result.passed
    assert any("record count mismatch" in p for p in result.problems), result.report
    assert "FAIL" in result.report


@pytest.mark.parametrize("bad_count", ["two", True, None])
def test_verify_rejects_non_integer_manifest_record_count(tmp_path, bad_count):
    """A missing/string/boolean record_count must be a manifest problem,
    not a silent bypass of truncation detection — bool is the sharp edge,
    since True == 1 would otherwise 'match' a one-record file."""
    sink = SQLiteSink(tmp_path / "count.db")
    gov = Governor(policy=ThresholdPolicy(), log=sink)
    gov.register(FixedCheck("check", True, 0.3))
    gov.evaluate("out", {"gate": "g"})
    gov.evaluate("out", {"gate": "g"})
    bundle = export(sink, tmp_path / "count-bundle")

    lines = (bundle / "records.jsonl").read_text(encoding="utf-8").splitlines()
    (bundle / "records.jsonl").write_text(lines[0] + "\n", encoding="utf-8")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if bad_count is None:
        manifest.pop("record_count")
    else:
        manifest["record_count"] = bad_count
    (bundle / "manifest.json").write_bytes(canonical_bytes(manifest))
    _remanifest(bundle)  # re-hash files + bundle, preserving the bad count

    result = verify(bundle)
    assert not result.passed
    assert any("record_count" in p for p in result.problems), result.report


def test_verify_rejects_schema_json_not_matching_supported_schema(cvar_bundle):
    """schema.json is semantically verified: swapping it for a different
    (or unusable) schema must FAIL, not silently fall back to the local
    schema."""
    bundle, _ = cvar_bundle
    (bundle / "schema.json").write_bytes(b"{}")  # valid JSON, wrong schema
    _remanifest(bundle)

    result = verify(bundle)
    assert not result.passed
    assert any("schema.json does not match" in p for p in result.problems), result.report


def test_verify_rejects_manifest_traversal_file_name(cvar_bundle):
    """A manifest entry that is not a flat bundle-member name (e.g. a
    traversal name) must fail structurally, never reach read_bytes()."""
    bundle, _ = cvar_bundle
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][".."] = "0" * 64  # points at the parent directory
    manifest["bundle_sha256"] = sha256_hex(canonical_bytes(manifest["files"]))
    (bundle / "manifest.json").write_bytes(canonical_bytes(manifest))

    result = verify(bundle)  # must not raise PermissionError/IsADirectoryError
    assert not result.passed
    assert any("unexpected file" in p for p in result.problems), result.report


def test_cli_verify_exit_1_on_malformed_manifest(tmp_path):
    gov = _cvar_governor(log=str(tmp_path / "mm.db"))
    gov.evaluate("out", {"gate": "apply"}, checks=["det_a"])
    bundle_dir = str(tmp_path / "mm-bundle")
    export(gov.log, Path(bundle_dir))
    (Path(bundle_dir) / "manifest.json").write_bytes(b"[]")
    assert cli_main(["audit", "verify", bundle_dir]) == 1


def test_cli_verify_exit_1_on_broken_records_stream(tmp_path):
    gov = _cvar_governor(log=str(tmp_path / "b.db"))
    gov.evaluate("out", {"gate": "apply"}, checks=["det_a"])
    bundle_dir = str(tmp_path / "b-bundle")
    export(gov.log, Path(bundle_dir))
    bundle = Path(bundle_dir)
    (bundle / "records.jsonl").write_bytes(b"{not-json}\n")
    _remanifest(bundle)
    assert cli_main(["audit", "verify", bundle_dir]) == 1


def test_verify_names_files_missing_from_disk(cvar_bundle, tmp_path):
    bundle, _ = cvar_bundle
    broken = tmp_path / "missing-file"
    broken.mkdir()
    for path in bundle.iterdir():
        if path.name != "pins.json":
            (broken / path.name).write_bytes(path.read_bytes())
    result = verify(broken)
    assert not result.passed
    assert any("pins.json listed in manifest but absent" in p for p in result.problems)


# ------------------------------------------------------------- actuarial


def test_chain_ladder_reproduces_hand_computed_factors():
    # f1 = (15+18)/(10+12) = 1.5 ; f2 = 18/15 = 1.2 (hand-computed).
    triangle = [[10.0, 15.0, 18.0], [12.0, 18.0], [9.0]]
    estimate = ibnr_ultimate(triangle)
    assert estimate.development_factors == (1.5, 1.2)
    assert estimate.ultimates == (18.0, pytest.approx(21.6), pytest.approx(16.2))
    assert estimate.ibnr == (0.0, pytest.approx(3.6), pytest.approx(7.2))
    with pytest.raises(ValueError, match="non-empty"):
        ibnr_ultimate([])


def test_kaplan_meier_reproduces_hand_computed_curve():
    # durations [2,3,3,5,7], reported [T,T,censored,T,censored]:
    # S(2)=4/5=0.8 ; S(3)=0.8*3/4=0.6 ; S(5)=0.6*1/2=0.3 (hand-computed).
    km = time_to_outcome([2, 3, 3, 5, 7], [True, True, False, True, False])
    assert km.times == (2, 3, 5)
    assert km.survival == (pytest.approx(0.8), pytest.approx(0.6), pytest.approx(0.3))
    assert km.median == 5          # first t with S <= 0.5
    assert km.dormant_after is None  # never reaches S <= 0.10
    with pytest.raises(ValueError, match="equal length"):
        time_to_outcome([1.0], [])