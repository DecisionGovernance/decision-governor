"""The --fail-on expression evaluator — Step 6 of Card G-5.

A tiny comparison language over a WHITELISTED metric vocabulary. No
eval(): the grammar is `<disjunction>` of `<conjunction>` of atomic
`field <op> number` comparisons, parsed by split-and-regex. The whitelist
doubles as the documented metric vocabulary, which keeps report fields
from proliferating namelessly.

The expression describes the FAILURE condition: it returns True (and the
breached clause) when CI should fail. Example:
    "cbw > 0.02 or injection_pass < 0.95"
"""
from __future__ import annotations

import operator
import re
from collections.abc import Mapping

# Short CI aliases -> canonical metric names emitted by the reports.
ALIASES: dict[str, str] = {
    "cbw": "cbw_rate",
    "injection_pass": "injection_pass",
    "right_reason": "caught_for_right_reason",
    "flip_rate": "verdict_flip_rate",
    "critical_flips": "critical_count",
    "cvar_ratio": "cvar_ratio",
    "undercall": "undercall_rate",
}

_COMPARATORS = {
    "<=": operator.le, ">=": operator.ge, "==": operator.eq,
    "!=": operator.ne, "<": operator.lt, ">": operator.gt,
}
_ATOM = re.compile(r"^([A-Za-z_][\w:]*)\s*(<=|>=|==|!=|<|>)\s*(-?\d+(?:\.\d+)?)$")


class FailOnError(ValueError):
    """A malformed expression or a reference to an unknown metric."""


def _resolve(field: str, metrics: Mapping[str, float]) -> float:
    key = ALIASES.get(field, field)
    if key not in metrics:
        raise FailOnError(
            f"unknown metric {field!r} (resolved {key!r}); available: "
            f"{', '.join(sorted(metrics))}"
        )
    return float(metrics[key])


def _atom_true(clause: str, metrics: Mapping[str, float]) -> bool:
    m = _ATOM.match(clause.strip())
    if not m:
        raise FailOnError(f"unparseable clause {clause!r} (expected 'field <op> number')")
    field, op, number = m.group(1), m.group(2), float(m.group(3))
    return bool(_COMPARATORS[op](_resolve(field, metrics), number))


def evaluate(expression: str, metrics: Mapping[str, float]) -> tuple[bool, str | None]:
    """Return (breached, breached_clause). breached is True when the
    failure expression holds; breached_clause names the disjunct that
    fired (its conjuncts joined by ' and ')."""
    for disjunct in expression.split(" or "):
        conjuncts = [c.strip() for c in disjunct.split(" and ")]
        if conjuncts and all(_atom_true(c, metrics) for c in conjuncts):
            return True, " and ".join(conjuncts)
    return False, None
