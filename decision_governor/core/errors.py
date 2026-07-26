"""Typed exceptions. Standard: every message says what the caller should *do*."""
from __future__ import annotations

from collections.abc import Iterable


class GovernorError(Exception):
    """Base class for all Decision Governor errors."""


class NoChecksRegistered(GovernorError):
    def __init__(self) -> None:
        super().__init__(
            "This Governor has no checks: register at least one check with "
            "gov.register() before calling evaluate()."
        )


class UnknownCheck(GovernorError):
    def __init__(self, name: str, registered: Iterable[str]) -> None:
        names = tuple(sorted(registered))
        listing = ", ".join(repr(n) for n in names) if names else "(none)"
        super().__init__(
            f"No check named {name!r} is registered. Registered checks: {listing}. "
            "Pass one of those names, or register the missing check with gov.register()."
        )
        self.name = name
        self.registered = names


class InvalidPolicy(GovernorError):
    def __init__(self, policy: object, missing: str = "judge") -> None:
        super().__init__(
            f"{type(policy).__name__} does not satisfy the Policy protocol: it has "
            f"no callable {missing}() method. Implement "
            f"{missing}(check_name, result, context) -> Decision on it, or pass a "
            "ThresholdPolicy instance."
        )
        self.missing = missing
