"""The monitoring hook: one pure function over sink.query() records.

Scheduling is the caller's job — e.g. cron:
    */30 * * * *  governor-monitor.py   # snapshot + notify if flagged
where governor-monitor.py builds the snapshot below and hands
report.lines to a notifier (TelegramSink for humans, CallbackSink in
tests).
"""
from __future__ import annotations

import json
import os
import urllib.request
import warnings
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from decision_governor.risk.credibility import buhlmann_straub


@dataclass(frozen=True)
class MonitorReport:
    total: int
    allow_rate: float
    scale_rate: float
    abstain_rate: float
    per_check_triggers: dict[str, int]     # non-ALLOW judgments per check
    abstention_trend_flag: bool            # second half notably worse
    outcome_reported_fraction: float
    gate_rates: dict[str, dict[str, float]]  # gate -> {rate, credibility, Z}

    @property
    def lines(self) -> list[str]:
        out = [
            (
                f"{self.total} decisions · allow {self.allow_rate:.2f} · "
                f"scale {self.scale_rate:.2f} · abstain {self.abstain_rate:.2f} · "
                f"outcomes reported {self.outcome_reported_fraction:.2f}"
            )
        ]
        for name, count in sorted(self.per_check_triggers.items()):
            out.append(f"check {name}: {count} non-allow judgments")
        for gate_name, stats in sorted(self.gate_rates.items()):
            out.append(
                f"gate {gate_name}: constrained {stats['rate']:.2f} "
                f"(credibility-weighted {stats['credibility']:.2f}, "
                f"Z={stats['Z']:.2f})"
            )
        if self.abstention_trend_flag:
            out.append("ABSTENTION TREND: second-half abstain rate is elevated")
        return out


def snapshot(records: Iterable[Mapping[str, Any]]) -> MonitorReport:
    """Rolling rates, per-check triggers, abstention trend, outcome
    fraction, and credibility-weighted per-gate rates with Z shown."""
    rows = list(records)
    total = len(rows)
    if total == 0:
        return MonitorReport(0, 0.0, 0.0, 0.0, {}, False, 0.0, {})

    def rate(decision: str, subset: list[Mapping[str, Any]]) -> float:
        if not subset:
            return 0.0
        return sum(1 for r in subset if r["decision"] == decision) / len(subset)

    triggers: dict[str, int] = {}
    for row in rows:
        for check in row.get("checks", []):
            if check["decision"] != "allow":
                triggers[check["name"]] = triggers.get(check["name"], 0) + 1

    half = total // 2
    first, second = rows[:half], rows[half:]
    trend = bool(
        half >= 2 and rate("abstain", second) > rate("abstain", first) + 0.15
    )

    reported = sum(
        1 for r in rows if (r.get("execution_outcome") or {}).get("reported")
    )

    by_gate: dict[str, tuple[int, int]] = {}
    for row in rows:
        gate_name = row.get("gate") or "(no gate)"
        n, constrained = by_gate.get(gate_name, (0, 0))
        by_gate[gate_name] = (
            n + 1, constrained + (1 if row["decision"] != "allow" else 0)
        )
    credibility = buhlmann_straub({g: v for g, v in by_gate.items()})
    gate_rates = {
        g: {
            "rate": constrained / n,
            "credibility": credibility[g].rate,
            "Z": credibility[g].Z,
        }
        for g, (n, constrained) in by_gate.items()
    }

    return MonitorReport(
        total=total,
        allow_rate=rate("allow", rows),
        scale_rate=rate("scale", rows),
        abstain_rate=rate("abstain", rows),
        per_check_triggers=triggers,
        abstention_trend_flag=trend,
        outcome_reported_fraction=reported / total,
        gate_rates=gate_rates,
    )


class CallbackSink:
    """Notification sink for tests: collects messages."""

    def __init__(self, fn: Callable[[str], None] | None = None) -> None:
        self.messages: list[str] = []
        self._fn = fn

    def notify(self, message: str) -> None:
        self.messages.append(message)
        if self._fn is not None:
            self._fn(message)


class TelegramSink:
    """Raw HTTP POST to the Telegram bot API — no SDK. Token from the
    TELEGRAM_BOT_TOKEN environment variable; chat id supplied."""

    def __init__(self, chat_id: str, token: str | None = None) -> None:
        self.chat_id = chat_id
        self.token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN")
        if not self.token:
            raise ValueError(
                "TelegramSink needs a bot token: set TELEGRAM_BOT_TOKEN or "
                "pass token= explicitly."
            )

    def notify(self, message: str) -> bool:
        """POST one report line to Telegram. A send failure is degraded to
        a warning and a False return — never raised — so a transient
        network error (rate limit, bad chat id, unreachable host) cannot
        abort a monitoring run partway through its report."""
        payload = json.dumps({"chat_id": self.chat_id, "text": message}).encode()
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request, timeout=10).read()  # pragma: no cover
        except OSError as exc:
            # URLError, HTTPError, and socket timeout are all OSError.
            warnings.warn(f"TelegramSink.notify failed: {exc}", stacklevel=2)
            return False
        return True
