"""The record builder: verdict + policy internals + context -> the
schema-v1.0 dict. A pure function, deliberately separated from writing,
so tests can assert record shape without a database.

The context itself never enters the record — only its digest over the
digestible view. Raw payloads (fact sources, style refs, tool-call
objects) stay with the caller.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from decision_governor.core.results import Verdict
from decision_governor.instrumentation.canonical import digest_of, digestible_view
from decision_governor.instrumentation.schema import SCHEMA_VERSION


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def policy_config(policy: Any) -> dict[str, Any]:
    """The policy's recomputation parameters, by known attribute.
    Everything the verifier needs to re-derive judgments — no more."""
    config: dict[str, Any] = {"policy": type(policy).__name__}
    for attr in (
        "alpha", "scale_at", "abstain_at", "scale_mitigation",
        "scale_friction", "ceiling_fraction", "default_cost", "top_k",
    ):
        value = getattr(policy, attr, None)
        if value is not None:
            config[attr] = value
    cost_map = getattr(policy, "cost_map", None)
    if cost_map:
        config["cost_map"] = dict(cost_map)
    costs = getattr(policy, "costs", None)
    if costs is not None and hasattr(costs, "as_dict"):
        config["costs"] = dict(costs.as_dict())
    return config


def build_record(
    verdict: Verdict,
    policy: Any,
    context: Mapping[str, Any],
    deployment: str,
    describes: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """One decision, exactly as the audit bundle will carry it."""
    describes = describes or {}
    checks: list[dict[str, Any]] = []
    risk_blocks = context.get("risk", {}) if isinstance(context, Mapping) else {}
    for record in verdict.records:
        entry: dict[str, Any] = {
            "name": record.name,
            "score": record.result.score,
            "confidence": record.result.confidence,
            "deterministic": record.deterministic,
            "decision": record.decision.value,
            "evidence": list(record.result.evidence),
            "describe": dict(
                describes.get(
                    record.name,
                    {"name": record.name, "deterministic": record.deterministic},
                )
            ),
        }
        per_check_risk = risk_blocks.get(record.name)
        if isinstance(per_check_risk, Mapping):
            entry["risk"] = dict(per_check_risk)
        checks.append(entry)

    gate_block = risk_blocks.get("__gate__")
    risk: dict[str, Any] = {
        **policy_config(policy),
        "decided_by": verdict.decided_by,
    }
    if isinstance(gate_block, Mapping):
        risk["gate_cvar"] = gate_block.get("gate_cvar")
        risk["enumeration"] = (
            "exact" if gate_block.get("exact") else "comonotonic_bound"
        )
        risk["gate"] = dict(gate_block)
    barred = [
        record.name
        for record in verdict.records
        if isinstance(risk_blocks.get(record.name), Mapping)
        and risk_blocks[record.name].get("allow_barred_by_ceiling")
    ]
    risk["allow_barred_by_ceiling"] = barred

    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": verdict.record_id,
        "recorded_at": now_iso(),
        "deployment": deployment,
        "gate": context.get("gate") if isinstance(context, Mapping) else None,
        "decision": verdict.decision.value,
        "decided_by": verdict.decided_by,
        "scale_path": verdict.scale_path,
        "aggregate_reason": verdict.aggregate_reason,
        "checks": checks,
        "risk": risk,
        "context_digest": digest_of(digestible_view(_without_risk(context))),
        "execution_outcome": {"reported": False, "revision": 0},
    }


def _without_risk(context: Mapping[str, Any]) -> dict[str, Any]:
    # The risk block is policy telemetry already captured in the record;
    # the digest covers the CALLER's context as supplied.
    if not isinstance(context, Mapping):
        return {}
    return {k: v for k, v in context.items() if k != "risk"}
