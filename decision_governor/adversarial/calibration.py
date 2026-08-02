"""Confident-but-wrong — Step 5 of Card G-5 (protected).

The petition's sharpest phrase as a number, computed over the decision
log: an ALLOW where every check was confident (min confidence >= floor)
and the reported outcome was bad. Plus a reliability table (binned
confidence vs observed bad-rate) — the picnic-forecaster audit, run on
ourselves — and per-check attribution.

The empty-case wording is a FIXTURE: with no reported outcomes the
statistic is UNDEFINED, not zero. The difference is honesty vs flattery,
and the pilot's early weeks live entirely in the empty case.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from decision_governor.adversarial.report import AdversarialReport

EMPTY_CASE = "0 reported outcomes — statistic undefined, not zero"


def _reported(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in records:
        outcome = r.get("execution_outcome") or {}
        if outcome.get("reported"):
            out.append(dict(r))
    return out


def confident_but_wrong(
    log: Iterable[Mapping[str, Any]],
    confidence_floor: float = 0.9,
    bins: int = 10,
) -> AdversarialReport:
    """`log` is any iterable of records (e.g. sink.query())."""
    if bins < 1:
        raise ValueError(f"bins must be >= 1, got {bins}")
    if not 0.0 <= confidence_floor <= 1.0:
        raise ValueError(f"confidence_floor must be in [0, 1], got {confidence_floor}")
    records = _reported(log)
    n_reported = len(records)
    params = {"confidence_floor": confidence_floor, "bins": bins}

    if n_reported == 0:
        # The statistic is undefined — deliberately DO NOT emit cbw_rate,
        # so a downstream --fail-on referencing it errors loudly rather
        # than reading a fabricated zero.
        return AdversarialReport(
            tool="calibration",
            seed=None,
            params=params,
            metrics={"n_reported": 0.0},
            findings=[],
            judgment=EMPTY_CASE,
        )

    cbw_cases: list[dict[str, Any]] = []
    per_check: dict[str, int] = {}
    binned = [[0, 0] for _ in range(bins)]  # [n_allow, n_bad] per confidence bin
    n_allow = 0

    for r in records:
        if r.get("decision") != "allow":
            continue
        n_allow += 1
        confidences = [float(c["confidence"]) for c in r.get("checks", [])]
        min_conf = min(confidences) if confidences else 0.0
        bad = (r.get("execution_outcome") or {}).get("ok") is False

        idx = min(bins - 1, int(min_conf * bins))
        binned[idx][0] += 1
        if bad:
            binned[idx][1] += 1

        if bad and confidences and min_conf >= confidence_floor:
            cbw_cases.append({
                "record_id": r.get("record_id"),
                "min_confidence": round(min_conf, 6),
                "checks": [c["name"] for c in r.get("checks", [])],
                "detail": (r.get("execution_outcome") or {}).get("detail", {}),
            })
            for c in r.get("checks", []):
                per_check[c["name"]] = per_check.get(c["name"], 0) + 1

    reliability = [
        {
            "lo": round(i / bins, 6),
            "hi": round((i + 1) / bins, 6),
            "n": n,
            "bad": bad,
            "observed_bad_rate": (bad / n if n else None),  # None, never a fabricated 0.0
        }
        for i, (n, bad) in enumerate(binned)
    ]

    metrics = {
        "cbw_rate": len(cbw_cases) / n_reported,
        "cbw_cases": float(len(cbw_cases)),
        "n_reported": float(n_reported),
        "n_allow": float(n_allow),
    }
    findings = (
        [{"kind": "cbw_case", **case} for case in cbw_cases]
        + [{"kind": "reliability_bin", **row} for row in reliability]
        + [{"kind": "per_check_attribution", "counts": per_check}]
    )
    judgment = (
        f"{len(cbw_cases)} confident-but-wrong ALLOW(s) at floor "
        f"{confidence_floor:.2f} over {n_reported} reported outcomes"
    )
    return AdversarialReport(
        tool="calibration",
        seed=None,
        params=params,
        metrics=metrics,
        findings=findings,
        judgment=judgment,
    )
