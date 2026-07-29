"""G-4 instrumentation: canonical serialization, the decision log,
outcomes, audit export/verify, monitors, and experimental actuarial
methods."""
from decision_governor.instrumentation.actuarial import (
    IBNREstimate,
    TimeToOutcome,
    ibnr_ultimate,
    time_to_outcome,
)
from decision_governor.instrumentation.audit import (
    BUNDLE_HASH_RECIPE,
    VerifyResult,
    export,
    verify,
)
from decision_governor.instrumentation.canonical import (
    canonical_bytes,
    digest_of,
    digestible_view,
    sha256_hex,
)
from decision_governor.instrumentation.errors import LogWriteError, UnknownRecord
from decision_governor.instrumentation.monitors import (
    CallbackSink,
    MonitorReport,
    TelegramSink,
    snapshot,
)
from decision_governor.instrumentation.outcomes import report_outcome
from decision_governor.instrumentation.records import build_record, policy_config
from decision_governor.instrumentation.schema import (
    SCHEMA,
    SCHEMA_VERSION,
    validate_record,
)
from decision_governor.instrumentation.sinks import (
    JsonlSink,
    Sink,
    SQLiteSink,
    resolve_sink,
)

__all__ = [
    "BUNDLE_HASH_RECIPE",
    "SCHEMA",
    "SCHEMA_VERSION",
    "CallbackSink",
    "IBNREstimate",
    "JsonlSink",
    "LogWriteError",
    "MonitorReport",
    "SQLiteSink",
    "Sink",
    "TelegramSink",
    "TimeToOutcome",
    "UnknownRecord",
    "VerifyResult",
    "build_record",
    "canonical_bytes",
    "digest_of",
    "digestible_view",
    "export",
    "ibnr_ultimate",
    "policy_config",
    "report_outcome",
    "resolve_sink",
    "sha256_hex",
    "snapshot",
    "time_to_outcome",
    "validate_record",
    "verify",
]
