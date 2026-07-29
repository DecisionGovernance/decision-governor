"""Decision-log sinks: the Sink protocol, SQLite default, JSONL append.

Postgres stays parked (v0.2); this protocol is its door.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from decision_governor.instrumentation.canonical import canonical_bytes
from decision_governor.instrumentation.errors import UnknownRecord


@runtime_checkable
class Sink(Protocol):
    def write(self, record: Mapping[str, Any]) -> None:
        """Persist one record atomically; raising is the failure signal."""

    def read(self, record_id: str) -> dict[str, Any]:
        """Return the record or raise UnknownRecord."""

    def query(
        self,
        from_ts: str | None = None,
        to_ts: str | None = None,
        gate: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Records in chronological order, optionally filtered."""


class SQLiteSink:
    """Default sink: one table, WAL mode, one INSERT per record —
    atomic for free."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS records ("
            "record_id TEXT PRIMARY KEY, recorded_at TEXT, gate TEXT, "
            "record TEXT NOT NULL)"
        )
        self._conn.commit()

    def write(self, record: Mapping[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO records (record_id, recorded_at, gate, record) "
            "VALUES (?, ?, ?, ?)",
            (
                record["record_id"],
                record.get("recorded_at"),
                record.get("gate"),
                canonical_bytes(dict(record)).decode("utf-8"),
            ),
        )
        self._conn.commit()

    def read(self, record_id: str) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT record FROM records WHERE record_id = ?", (record_id,)
        ).fetchone()
        if row is None:
            raise UnknownRecord(record_id)
        loaded: dict[str, Any] = json.loads(row[0])
        return loaded

    def query(
        self,
        from_ts: str | None = None,
        to_ts: str | None = None,
        gate: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        sql = "SELECT record FROM records WHERE 1=1"
        params: list[str] = []
        if from_ts is not None:
            sql += " AND recorded_at >= ?"
            params.append(from_ts)
        if to_ts is not None:
            sql += " AND recorded_at <= ?"
            params.append(to_ts)
        if gate is not None:
            sql += " AND gate = ?"
            params.append(gate)
        sql += " ORDER BY recorded_at"
        for row in self._conn.execute(sql, params):
            yield json.loads(row[0])


class JsonlSink:
    """Append-only: one canonical record per line. Re-writing a record
    (the outcome callback) appends a new line; reads and queries resolve
    last-write-wins by record_id."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write(self, record: Mapping[str, Any]) -> None:
        with open(self.path, "ab") as handle:
            handle.write(canonical_bytes(dict(record)) + b"\n")

    def _latest(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        if not self.path.exists():
            return latest
        with open(self.path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    record = json.loads(line)
                    latest[record["record_id"]] = record
        return latest

    def read(self, record_id: str) -> dict[str, Any]:
        record = self._latest().get(record_id)
        if record is None:
            raise UnknownRecord(record_id)
        return record

    def query(
        self,
        from_ts: str | None = None,
        to_ts: str | None = None,
        gate: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        records = sorted(
            self._latest().values(), key=lambda r: r.get("recorded_at") or ""
        )
        for record in records:
            ts = record.get("recorded_at") or ""
            if from_ts is not None and ts < from_ts:
                continue
            if to_ts is not None and ts > to_ts:
                continue
            if gate is not None and record.get("gate") != gate:
                continue
            yield record


def resolve_sink(log: Any) -> Sink | None:
    """Governor(log=...) accepts a Sink, a path string (-> SQLiteSink),
    or None."""
    if log is None:
        return None
    if isinstance(log, (str, Path)):
        return SQLiteSink(log)
    if isinstance(log, Sink):
        return log
    raise TypeError(
        f"log must be a Sink, a database path, or None; got {type(log).__name__}. "
        "Pass e.g. log='decisions.db' or an object implementing "
        "write/read/query."
    )
