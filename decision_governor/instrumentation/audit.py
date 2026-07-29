"""Audit export and verify: the bundle, and the round-trip that is the
G-4 gate.

The bundle hash recipe (precision trap #2): bundle_sha256 is computed
over the CANONICAL SERIALIZATION of the file-hash mapping — never over
concatenated file bytes — and the manifest states the recipe in-band
("bundle_hash_recipe") so an independent implementer can verify without
reading this source. "Check our math", not "trust our tool".
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from decision_governor import __version__
from decision_governor.instrumentation import _recompute
from decision_governor.instrumentation.canonical import canonical_bytes, sha256_hex
from decision_governor.instrumentation.records import now_iso
from decision_governor.instrumentation.schema import (
    SCHEMA,
    SCHEMA_VERSION,
    validate_record,
)
from decision_governor.instrumentation.sinks import Sink

BUNDLE_HASH_RECIPE = "sha256(canonical_bytes(files))"
_BUNDLE_FILES = ("records.jsonl", "schema.json", "pins.json", "config.json")


def export(
    sink: Sink,
    out_dir: str | Path,
    from_ts: str | None = None,
    to_ts: str | None = None,
    redact_costs: bool = False,
) -> Path:
    """Write the audit bundle; the manifest is built last, over the
    hashes of everything else."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = list(sink.query(from_ts=from_ts, to_ts=to_ts))

    lines = b"".join(canonical_bytes(record) + b"\n" for record in records)
    (out / "records.jsonl").write_bytes(lines)

    (out / "schema.json").write_bytes(canonical_bytes(SCHEMA))

    pins: dict[str, Any] = {}
    for record in records:
        for check in record.get("checks", []):
            pins.setdefault(check["name"], check.get("describe", {}))
    (out / "pins.json").write_bytes(canonical_bytes(pins))

    config = _bundle_config(records, redact_costs)
    (out / "config.json").write_bytes(canonical_bytes(config))

    files = {
        name: sha256_hex((out / name).read_bytes()) for name in _BUNDLE_FILES
    }
    manifest = {
        "files": files,
        "bundle_sha256": sha256_hex(canonical_bytes(files)),
        "bundle_hash_recipe": BUNDLE_HASH_RECIPE,
        "tool_version": __version__,
        "exported_at": now_iso(),
        "record_count": len(records),
    }
    (out / "manifest.json").write_bytes(canonical_bytes(manifest))
    return out


def _bundle_config(
    records: Iterable[Mapping[str, Any]], redact_costs: bool
) -> dict[str, Any]:
    config: dict[str, Any] = {"costs_redacted": redact_costs}
    for record in records:
        risk = record.get("risk") or {}
        for key in (
            "policy", "alpha", "scale_at", "abstain_at", "scale_mitigation",
            "scale_friction", "ceiling_fraction", "cost_map", "default_cost",
        ):
            if key in risk and key not in config:
                config[key] = risk[key]
        if "costs" in risk and "costs" not in config:
            costs = dict(risk["costs"])
            if redact_costs:
                # Names stay (the vocabulary is the point); values go.
                costs = {name: None for name in costs}
            config["costs"] = costs
        if "deployment" not in config and record.get("deployment"):
            config["deployment"] = record["deployment"]
    return config


def _record_config(
    record: Mapping[str, Any], bundle_config: Mapping[str, Any]
) -> dict[str, Any]:
    """Recompute parameters for ONE record, read from that record's own
    stored policy block — never a bundle-wide collapse.

    build_record already writes each decision's full policy config into
    record['risk'] (records.py). Taking the parameters from there lets a
    log that spans a policy change verify each record against the policy
    it was actually decided under, instead of judging every record by the
    first record's thresholds. Cost redaction stays bundle-global: when
    the bundle withholds cost values, the economic recompute is skipped
    here exactly as it is for the declared config."""
    risk = record.get("risk") or {}
    redacted = bool(bundle_config.get("costs_redacted"))
    config: dict[str, Any] = {"costs_redacted": redacted}
    for key in (
        "policy", "alpha", "scale_at", "abstain_at", "scale_mitigation",
        "scale_friction", "ceiling_fraction", "cost_map", "default_cost",
    ):
        if key in risk:
            config[key] = risk[key]
    costs = risk.get("costs")
    if isinstance(costs, Mapping):
        config["costs"] = (
            {name: None for name in costs} if redacted else dict(costs)
        )
    return config


class VerifyResult:
    def __init__(self) -> None:
        self.record_count = 0
        self.recomputed = 0
        self.mismatches: list[dict[str, Any]] = []
        self.problems: list[str] = []
        self.pins: dict[str, Any] = {}
        self.config_digest_ok = False
        self.notes: list[str] = []

    @property
    def passed(self) -> bool:
        return not self.mismatches and not self.problems

    @property
    def report(self) -> str:
        lines = [
            (
                f"{self.record_count} records · {self.recomputed} deterministic "
                f"verdicts recomputed · {len(self.mismatches)} mismatches"
            )
        ]
        if self.pins:
            lines.append(
                "pins: " + ", ".join(
                    f"{name}" for name in sorted(self.pins)
                )
            )
        lines.append(
            "config digest matches" if self.config_digest_ok
            else "CONFIG DIGEST MISMATCH"
        )
        lines.extend(self.notes)
        for problem in self.problems:
            lines.append(f"PROBLEM: {problem}")
        for mismatch in self.mismatches:
            lines.append(
                f"MISMATCH {mismatch['record_id']}: "
                + "; ".join(
                    f"{field} stored={stored!r} recomputed={recomputed!r}"
                    for field, (stored, recomputed) in mismatch["fields"].items()
                )
            )
        lines.append("PASS" if self.passed else "FAIL")
        return "\n".join(lines)


def verify(bundle_dir: str | Path) -> VerifyResult:
    """Four passes: hashes, schema, recompute, report. Exit-0 iff PASS
    is the CLI's job; this returns the structured result."""
    bundle = Path(bundle_dir)
    result = VerifyResult()

    # Pass 1 — hashes: every file hash + the bundle hash, per the recipe.
    try:
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        result.problems.append("manifest.json missing — not an audit bundle")
        return result
    except json.JSONDecodeError as exc:
        result.problems.append(f"manifest.json is not valid JSON ({exc})")
        return result
    if not isinstance(manifest, dict):
        result.problems.append(
            "manifest.json is not a JSON object — not an audit bundle"
        )
        return result
    stored_files = manifest.get("files", {})
    if not isinstance(stored_files, dict):
        result.problems.append("manifest.json 'files' is not a JSON object")
        return result
    # The manifest does not get to define the bundle's membership: the
    # required set is fixed here, so an adversary cannot omit a member
    # (e.g. pins.json's model provenance, or schema.json), re-seal the
    # bundle hash over what remains, and still earn a PASS. Membership is
    # also EXACT: an unexpected key (a traversal name like "..", a subdir,
    # an absolute path) is rejected before any read, so a malformed name
    # never reaches read_bytes() and crashes the verifier.
    missing_required = [name for name in _BUNDLE_FILES if name not in stored_files]
    unexpected = [name for name in stored_files if name not in _BUNDLE_FILES]
    for name in missing_required:
        result.problems.append(
            f"required file {name} not listed in manifest — bundle incomplete"
        )
    for name in unexpected:
        result.problems.append(
            f"manifest lists unexpected file {name!r} — bundle members are fixed"
        )
    if missing_required or unexpected:
        # Structural manifest problem: fail before touching the filesystem.
        return result
    actual_files: dict[str, str] = {}
    for name, stored_hash in stored_files.items():
        path = bundle / name
        if not path.exists():
            result.problems.append(f"file {name} listed in manifest but absent")
            continue
        actual = sha256_hex(path.read_bytes())
        actual_files[name] = actual
        if actual != stored_hash:
            result.problems.append(
                f"file {name} hash mismatch: manifest {stored_hash} != actual {actual}"
            )
    recomputed_bundle = sha256_hex(canonical_bytes(actual_files))
    if recomputed_bundle != manifest.get("bundle_sha256"):
        result.problems.append(
            f"bundle hash mismatch: manifest {manifest.get('bundle_sha256')} "
            f"!= recomputed {recomputed_bundle} (recipe: {BUNDLE_HASH_RECIPE})"
        )
    result.config_digest_ok = (
        stored_files.get("config.json") == actual_files.get("config.json")
    )
    if any("absent" in problem for problem in result.problems):
        # A manifest-promised file is missing on disk: fail with the
        # pass-1 specifics rather than crashing when a later pass reads it.
        return result

    # Pass 2 — schema then records. The bundled schema must BE the
    # supported schema, not merely hash to something: otherwise a bundle
    # could advertise a different or unusable schema while the verifier
    # silently applies its local one.
    try:
        bundled_schema = json.loads((bundle / "schema.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.problems.append(f"schema.json is not valid JSON ({exc})")
        return result
    if bundled_schema != SCHEMA:
        result.problems.append(
            f"schema.json does not match the supported v{SCHEMA_VERSION} "
            "record schema"
        )
        return result

    # Every line is parsed defensively: a syntactically broken stream, a
    # non-object record, or a schema-invalid record must each yield a
    # structured FAIL, never a traceback, because recomputation assumes a
    # list of schema-shaped objects.
    records: list[dict[str, Any]] = []
    schema_ok = True
    lines = (bundle / "records.jsonl").read_text(encoding="utf-8").splitlines()
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            result.problems.append(f"records.jsonl line {lineno}: invalid JSON ({exc})")
            schema_ok = False
            continue
        if not isinstance(parsed, dict):
            result.problems.append(
                f"records.jsonl line {lineno}: record is not a JSON object"
            )
            schema_ok = False
            continue
        for problem in validate_record(parsed):
            result.problems.append(f"record {parsed.get('record_id')}: {problem}")
            schema_ok = False
        records.append(parsed)
    result.record_count = len(records)
    # The sealed count is the truncation tripwire (a dropped line that
    # reuses existing checks slips past pin reconciliation), so it must be
    # a real integer AND equal — a missing, string, or boolean count is a
    # manifest problem, not a reason to skip the check. (bool is an int
    # subclass, and True == 1, so it must be excluded explicitly.)
    manifest_count = manifest.get("record_count")
    if not isinstance(manifest_count, int) or isinstance(manifest_count, bool):
        result.problems.append(
            f"manifest record_count is missing or not an integer: {manifest_count!r}"
        )
        schema_ok = False
    elif manifest_count != result.record_count:
        result.problems.append(
            f"record count mismatch: manifest {manifest_count} "
            f"!= {result.record_count} records in records.jsonl"
        )
        schema_ok = False
    if not schema_ok:
        # A broken stream, non-object record, or schema-invalid record
        # cannot be safely recomputed; fail with the pass-2 specifics
        # instead of crashing in pass 3.
        return result

    # Pass 3 — recompute, independently, from stored fields + config.
    # The bundle config carries the redaction flag and the declared-config
    # digest; the per-record policy parameters come from each record.
    try:
        bundle_config = json.loads((bundle / "config.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.problems.append(f"config.json is not valid JSON ({exc})")
        return result
    if not isinstance(bundle_config, dict):
        result.problems.append("config.json is not a JSON object")
        return result

    # Report pins are DERIVED from the records, never trusted from the
    # detached pins.json: the summary is then reconciled against them, so a
    # tampered or emptied summary is a problem instead of a silent omission.
    expected_pins: dict[str, Any] = {}
    for record in records:
        for check in record.get("checks", []):
            expected_pins.setdefault(check["name"], check.get("describe", {}))
    result.pins = expected_pins
    try:
        stored_pins = json.loads((bundle / "pins.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.problems.append(f"pins.json is not valid JSON ({exc})")
    else:
        if not isinstance(stored_pins, dict):
            result.problems.append("pins.json is not a JSON object")
        elif stored_pins != expected_pins:
            result.problems.append(
                "pins.json does not match the check descriptions in records.jsonl"
            )

    if bundle_config.get("costs_redacted"):
        result.notes.append(
            "costs redacted: economic recompute skipped, composition verified"
        )
    model_backed = 0
    for record in records:
        derived = _recompute.recompute_record(
            record, _record_config(record, bundle_config)
        )
        model_backed += sum(
            1 for check in record["checks"] if not check["deterministic"]
        )
        if not derived["judgeable"] and derived["decision"] is None:
            continue  # redacted or foreign policy: composition-only below
        result.recomputed += 1
        fields: dict[str, tuple[Any, Any]] = {}
        if derived["decision"] is not None and derived["decision"] != record["decision"]:
            fields["decision"] = (record["decision"], derived["decision"])
        if (
            derived["decided_by"] is not None
            and derived["decided_by"] != record["decided_by"]
        ):
            fields["decided_by"] = (record["decided_by"], derived["decided_by"])
        stored_barred = sorted(record.get("risk", {}).get("allow_barred_by_ceiling", []))
        if derived["allow_barred_by_ceiling"] != stored_barred:
            fields["allow_barred_by_ceiling"] = (
                stored_barred, derived["allow_barred_by_ceiling"]
            )
        stored_gate_cvar = record.get("risk", {}).get("gate_cvar")
        if (
            derived["gate_cvar"] is not None
            and stored_gate_cvar is not None
            and abs(derived["gate_cvar"] - float(stored_gate_cvar)) > 1e-9
        ):
            fields["gate_cvar"] = (stored_gate_cvar, derived["gate_cvar"])
        stored_enum = record.get("risk", {}).get("enumeration")
        if (
            derived["enumeration"] is not None
            and stored_enum is not None
            and derived["enumeration"] != stored_enum
        ):
            fields["enumeration"] = (stored_enum, derived["enumeration"])
        for check in record["checks"]:
            recomputed = derived["per_check"] and derived["per_check"].get(check["name"])
            if recomputed is not None and recomputed != check["decision"]:
                fields[f"check:{check['name']}"] = (check["decision"], recomputed)
        if fields:
            result.mismatches.append(
                {"record_id": record["record_id"], "fields": fields}
            )
    if model_backed:
        result.notes.append(
            f"{model_backed} model-backed check results re-verified from stored "
            "CheckResults — the models are not in the bundle"
        )

    # Pass 4 — the report string is assembled by VerifyResult.report.
    return result
