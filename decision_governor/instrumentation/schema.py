"""Record schema v1.0, embedded in the package so audit bundles carry it.

Validation is a minimal hand-rolled checker (the base install stays
dependency-light); it verifies required keys and primitive types, not
full JSON Schema semantics.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SCHEMA_VERSION = "1.0"

SCHEMA: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "type": "object",
    "required": {
        "schema_version": "string",
        "record_id": "string",
        "recorded_at": "string",
        "deployment": "string",
        "gate": "string_or_null",
        "decision": "string",
        "decided_by": "string",
        "scale_path": "string_or_null",
        "aggregate_reason": "string_or_null",
        "checks": "array",
        "risk": "object",
        "context_digest": "string",
        "execution_outcome": "object",
    },
    "check_entry_required": {
        "name": "string",
        "score": "number",
        "confidence": "number",
        "deterministic": "boolean",
        "decision": "string",
        "evidence": "array",
        "describe": "object",
    },
    "enums": {
        "decision": ["allow", "scale", "abstain"],
        "decided_by": ["per_check", "aggregate", "ceiling"],
    },
}

_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "string_or_null": lambda v: v is None or isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def validate_record(record: Mapping[str, Any]) -> list[str]:
    """Return a list of problems; empty list means the record validates."""
    problems: list[str] = []
    for key, kind in SCHEMA["required"].items():
        if key not in record:
            problems.append(f"missing required field {key!r}")
        elif not _TYPE_CHECKS[kind](record[key]):
            problems.append(f"field {key!r} is not of type {kind}")
    for field, allowed in SCHEMA["enums"].items():
        if field in record and record[field] not in allowed:
            problems.append(f"field {field!r} value {record[field]!r} not in {allowed}")
    for index, entry in enumerate(record.get("checks", []) or []):
        if not isinstance(entry, dict):
            problems.append(f"checks[{index}] is not an object")
            continue
        for key, kind in SCHEMA["check_entry_required"].items():
            if key not in entry:
                problems.append(f"checks[{index}] missing {key!r}")
            elif not _TYPE_CHECKS[kind](entry[key]):
                problems.append(f"checks[{index}].{key} is not of type {kind}")
    return problems
