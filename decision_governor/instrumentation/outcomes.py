"""The outcome callback: the ONLY mutation in the system.

An execution outcome amends a stored record's execution_outcome block —
and nothing else. The verifier treats that block as outside the
recomputation boundary: verdicts are recomputed from decision-time
fields; outcomes are provenance, not inputs.

Conventional detail keys — documented, deliberately NOT validated
(convention, not schema, so other deployments aren't wearing
First-Qualified's shoes):
  user_edit_distance: how much the human changed the output post-ALLOW
  employer_response:  what came back, if anything
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from decision_governor.instrumentation.records import now_iso
from decision_governor.instrumentation.sinks import Sink


def report_outcome(
    sink: Sink,
    record_id: str,
    ok: bool,
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Idempotent last-write-wins; `revision` counts the writes so an
    auditor can see that an outcome was amended."""
    record = sink.read(record_id)  # UnknownRecord if absent
    previous = record.get("execution_outcome") or {}
    record["execution_outcome"] = {
        "reported": True,
        "ok": ok,
        "reported_at": now_iso(),
        "detail": dict(detail or {}),
        "revision": int(previous.get("revision", 0)) + 1,
    }
    sink.write(record)
    return record
