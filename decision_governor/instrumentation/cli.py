"""The `governor` console script: audit export | audit verify.

argparse only — no click dependency. Exit code 0 iff verify PASSes.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence

from decision_governor.instrumentation.audit import export, verify
from decision_governor.instrumentation.sinks import SQLiteSink


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="governor", description="Decision Governor instrumentation tools."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="audit bundle tools")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)

    exp = audit_sub.add_parser("export", help="export an audit bundle")
    exp.add_argument("--db", required=True, help="path to the decision log")
    exp.add_argument("-o", "--out", required=True, help="bundle output directory")
    exp.add_argument("--from", dest="from_ts", default=None, help="ISO lower bound")
    exp.add_argument("--to", dest="to_ts", default=None, help="ISO upper bound")
    exp.add_argument(
        "--redact-costs", action="store_true",
        help="ship cost names but not values",
    )

    ver = audit_sub.add_parser("verify", help="verify an audit bundle")
    ver.add_argument("bundle", help="bundle directory to verify")

    args = parser.parse_args(argv)
    if args.audit_command == "export":
        out = export(
            SQLiteSink(args.db), args.out,
            from_ts=args.from_ts, to_ts=args.to_ts,
            redact_costs=args.redact_costs,
        )
        print(f"bundle written to {out}")
        return 0
    result = verify(args.bundle)
    print(result.report)
    return 0 if result.passed else 1
