"""Command-line entry point for project diagnostics."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .doctor import DoctorReport, run_doctor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rrt",
        description="Research hardware bring-up utilities",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser(
        "doctor",
        help="inspect the local environment without opening a motor bus",
    )
    doctor.add_argument(
        "--manifest",
        type=Path,
        default=Path("configs/hardware_manifest.yaml"),
        help="hardware manifest to validate (default: configs/hardware_manifest.yaml)",
    )
    doctor.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        report = run_doctor(args.manifest)
        if args.json_output:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print_human_report(report)
        return report.exit_code
    raise AssertionError(f"unhandled command: {args.command}")


def print_human_report(report: DoctorReport) -> None:
    print("Real-time recovery diagnostics")
    for check in report.checks:
        print(f"[{check.status.upper():7}] {check.name}: {check.summary}")
        for detail in check.details:
            print(f"          {detail}")
    print(f"Overall: {report.overall_status}")


if __name__ == "__main__":
    raise SystemExit(main())
