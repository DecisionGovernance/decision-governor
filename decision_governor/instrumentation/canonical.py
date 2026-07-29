"""Canonical serialization: the single function everything downstream
hashes. Precision trap #1 lives here — if export and verify ever
serialize differently (key order, float formatting, unicode), the
round-trip fails mysteriously. One function, imported by both sides;
never inline json.dumps anywhere else in the instrumentation card.

Floats rely on Python's repr-shortest round-trip formatting (the
json module's default) — documented here as part of the recipe.
NaN/Inf are forbidden (allow_nan=False): they would break
cross-verifier equality.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def canonical_bytes(obj: Any) -> bytes:
    """Deterministic bytes for a JSON-representable object.

    sort_keys + minimal separators + UTF-8 (ensure_ascii=False) +
    repr-shortest floats + NaN/Inf forbidden. Non-JSON values raise
    TypeError — callers wanting lenience go through digestible_view().
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_of(obj: Any) -> str:
    """sha256 over the canonical bytes."""
    return sha256_hex(canonical_bytes(obj))


def digestible_view(obj: Any) -> Any:
    """The context policy: JSON-representable values pass through;
    objects offering digest() or a dict form contribute that; everything
    else becomes the declared placeholder '<unserializable: TypeName>'.
    Raw non-JSON payloads therefore never reach a record."""
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        # NaN/Inf would poison canonical_bytes downstream.
        if not math.isfinite(obj):
            return f"<non-finite: {obj!r}>"
        return obj
    if isinstance(obj, dict):
        return {str(key): digestible_view(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [digestible_view(item) for item in obj]
    digest = getattr(obj, "digest", None)
    if callable(digest):
        return {"digest": str(digest()), "type": type(obj).__name__}
    as_dict = getattr(obj, "__dict__", None)
    if isinstance(as_dict, dict) and as_dict:
        return {
            "type": type(obj).__name__,
            "fields": digestible_view(as_dict),
        }
    return f"<unserializable: {type(obj).__name__}>"
