from __future__ import annotations

import argparse
import json
from pathlib import Path

from datumguard.frame_opensees import run_opensees_parity_benchmark

DEFAULT_OUTPUT = Path("artifacts/benchmarks/frame-opensees-parity.json")
DEFAULT_PACKAGE_OUTPUT = Path("src/datumguard/data/frame_opensees_parity.json")


def _write_report(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{payload}\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the genuine OpenSeesPy parity benchmark for FrameGuard."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"audit JSON path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--package-output",
        type=Path,
        default=DEFAULT_PACKAGE_OUTPUT,
        help=f"packaged evidence JSON path (default: {DEFAULT_PACKAGE_OUTPUT})",
    )
    parser.add_argument(
        "--no-package-copy",
        action="store_true",
        help="do not mirror the report into the datumguard package",
    )
    parser.add_argument(
        "--allow-unavailable",
        action="store_true",
        help="return exit code 0 for UNAVAILABLE while preserving structured status",
    )
    args = parser.parse_args()

    report = run_opensees_parity_benchmark()
    payload = json.dumps(
        report.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True
    )
    _write_report(args.output, payload)
    if not args.no_package_copy:
        _write_report(args.package_output, payload)

    summary = report.summary
    print(
        f"OpenSees parity {report.status}: "
        f"{summary['passed_count']} passed, {summary['failed_count']} failed, "
        f"{summary['skipped_count']} skipped"
    )
    print(f"Audit report: {args.output.resolve()}")
    if not args.no_package_copy:
        print(f"Package report: {args.package_output.resolve()}")
    if report.status == "PASSED":
        return 0
    if report.status == "UNAVAILABLE" and args.allow_unavailable:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
