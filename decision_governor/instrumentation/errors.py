"""Instrumentation errors. House standard: say what the caller should do."""
from __future__ import annotations

from typing import TYPE_CHECKING

from decision_governor.core.errors import GovernorError

if TYPE_CHECKING:
    from decision_governor.core.results import Verdict


class LogWriteError(GovernorError):
    """A record failed to persist. Loud, but not lossy: the verdict was
    fully formed before the write attempt and rides on the error as
    err.verdict, so a caller who catches this still has the decision."""

    def __init__(self, verdict: Verdict, cause: Exception) -> None:
        super().__init__(
            f"decision record {verdict.record_id} could not be written to the "
            f"log ({type(cause).__name__}: {cause}). The verdict itself is "
            "attached as err.verdict — act on it, then repair the sink."
        )
        self.verdict = verdict
        self.cause = cause


class UnknownRecord(GovernorError):
    def __init__(self, record_id: str) -> None:
        super().__init__(
            f"no record with id {record_id!r} exists in this sink. Use the "
            "record_id from the Verdict returned by evaluate(), and confirm "
            "you are reading the same sink the Governor writes to."
        )
        self.record_id = record_id
