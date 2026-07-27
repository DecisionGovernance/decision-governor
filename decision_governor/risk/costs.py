"""CostStructure: named error costs, in the domain's own units.

The *names* are the user's vocabulary (`unsupported_claim`,
`injected_action`) — the SDK never hardcodes error taxonomies, because
cost denomination in the domain's own units is the "real-world cost
structures" commitment made literal.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


class CostStructure:
    """Frozen mapping of cost names to strictly positive costs.

    `abstention` is mandatory by design: always-abstaining must never be
    free, because a governor that can silently refuse everything isn't
    governing, it's abdicating.
    """

    __slots__ = ("_costs",)
    _costs: Mapping[str, float]

    def __init__(self, **named_costs: float) -> None:
        if "abstention" not in named_costs:
            raise ValueError(
                "abstention cost is mandatory — a policy where refusing is free "
                "will always refuse. Pass abstention=<cost of declining, in your "
                "own units> alongside your error costs."
            )
        for name, value in named_costs.items():
            if not value > 0:
                raise ValueError(
                    f"cost {name!r} must be strictly positive, got {value!r} — "
                    "a zero cost makes that error invisible to the policy."
                )
        object.__setattr__(self, "_costs", MappingProxyType(dict(named_costs)))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("CostStructure is frozen")

    def __contains__(self, name: object) -> bool:
        return name in self._costs

    def __repr__(self) -> str:
        inner = ", ".join(f"{k}={v}" for k, v in sorted(self._costs.items()))
        return f"CostStructure({inner})"

    def get(self, name: str) -> float:
        try:
            return float(self._costs[name])
        except KeyError:
            raise KeyError(
                f"no cost named {name!r}; defined costs: "
                f"{', '.join(repr(n) for n in self.names)}. Add it to the "
                "CostStructure or fix the cost_map entry that references it."
            ) from None

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._costs))

    @property
    def abstention(self) -> float:
        return float(self._costs["abstention"])

    @property
    def total_exposure(self) -> float:
        """Sum of the error costs (abstention is a choice, not an error)."""
        return float(sum(v for k, v in self._costs.items() if k != "abstention"))

    def as_dict(self) -> Mapping[str, float]:
        return self._costs
