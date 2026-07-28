"""output_domain: deterministic safety check on output shape.

Score is the fraction of rules violated — the one deterministic check
where graduated score is natural — with each violated rule named.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from decision_governor.checks._base import CheckBase, extract_text
from decision_governor.core.types import CheckResult

_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class OutputDomain(CheckBase):
    """Length bounds, required/forbidden sections, and a minimal
    JSON-schema subset (`required` + `properties.<name>.type`) when the
    output is structured. Constructor rules merge with per-call
    context["domain_rules"] (context wins on conflicts)."""

    name = "output_domain"
    deterministic = True

    def __init__(
        self,
        min_length: int | None = None,
        max_length: int | None = None,
        required_sections: Sequence[str] = (),
        forbidden_sections: Sequence[str] = (),
        json_schema: Mapping[str, Any] | None = None,
    ) -> None:
        self._rules: dict[str, Any] = {
            "min_length": min_length,
            "max_length": max_length,
            "required_sections": tuple(required_sections),
            "forbidden_sections": tuple(forbidden_sections),
            "json_schema": dict(json_schema) if json_schema else None,
        }

    def _config(self) -> dict[str, Any]:
        return {k: v for k, v in self._rules.items() if v}

    def _merged_rules(self, context: Mapping[str, Any]) -> dict[str, Any]:
        rules = dict(self._rules)
        rules.update(context.get("domain_rules", {}))
        return rules

    def run(self, output: Any, context: Mapping[str, Any]) -> CheckResult:
        rules = self._merged_rules(context)
        text = extract_text(output)
        violations: list[str] = []
        total = 0

        if rules.get("min_length") is not None:
            total += 1
            if len(text) < rules["min_length"]:
                violations.append(
                    f"min_length: {len(text)} chars < required {rules['min_length']}"
                )
        if rules.get("max_length") is not None:
            total += 1
            if len(text) > rules["max_length"]:
                violations.append(
                    f"max_length: {len(text)} chars > allowed {rules['max_length']}"
                )
        for section in rules.get("required_sections", ()):
            total += 1
            if section.lower() not in text.lower():
                violations.append(f"required section missing: {section!r}")
        for section in rules.get("forbidden_sections", ()):
            total += 1
            if section.lower() in text.lower():
                violations.append(f"forbidden section present: {section!r}")

        schema = rules.get("json_schema")
        if schema:
            total += 1
            violations.extend(self._schema_violations(output, schema))

        if total == 0:
            return self.skip("no domain rules configured")
        # A schema can contribute several named violations but counts once.
        score = min(len(violations), total) / total
        return CheckResult(score=score, confidence=1.0, evidence=violations)

    @staticmethod
    def _schema_violations(output: Any, schema: Mapping[str, Any]) -> list[str]:
        data: Any = output
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                return ["json_schema: output is not valid JSON"]
        if not isinstance(data, Mapping):
            return ["json_schema: output is not a JSON object"]
        found: list[str] = []
        for field in schema.get("required", ()):
            if field not in data:
                found.append(f"json_schema: required property missing: {field!r}")
        for field, spec in schema.get("properties", {}).items():
            expected = _JSON_TYPES.get(spec.get("type", ""))
            if field in data and expected is not None:
                value = data[field]
                ok = isinstance(value, expected)
                if expected is int and isinstance(value, bool):
                    ok = False  # bool is not an integer for schema purposes
                if not ok:
                    found.append(
                        f"json_schema: property {field!r} is not of type "
                        f"{spec['type']!r}"
                    )
        return found
