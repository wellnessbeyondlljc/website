#!/usr/bin/env python3
"""
WAI Integration Test Report Generator

Reads results.json produced by run-integration-tests.sh and writes
a human-readable text report. Falls back to running the public
integration suite directly if results.json is not present.

Usage:
    python3 tests/integration/runner.py --mode=all --output=report.txt
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path


def run_tests_directly() -> tuple[str, dict]:
    """Run the stable public integration suite and return (output, summary)."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/behavioral/test_public_reorg_structure.py",
            "tests/behavioral/test_spoke_structure.py",
            "tests/behavioral/test_teaching_adoption.py",
            "-q",
        ],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr

    import re

    passed_match = re.search(r"(\d+)\s+passed", output)
    failed_match = re.search(r"(\d+)\s+failed", output)
    skipped_match = re.search(r"(\d+)\s+skipped", output)

    passed = int(passed_match.group(1)) if passed_match else 0
    failed = int(failed_match.group(1)) if failed_match else 0
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    total = passed + failed + skipped

    summary = {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }
    return output, summary


def main():
    parser = argparse.ArgumentParser(description="WAI integration test report generator")
    parser.add_argument("--mode", default="all", help="Test mode")
    parser.add_argument("--output", default="report.txt", help="Output file path")
    args = parser.parse_args()

    results_file = Path("results.json")
    if results_file.exists():
        with open(results_file) as f:
            data = json.load(f)
        output = data.get("output", "")
        summary = data.get("summary", {})
    else:
        output, summary = run_tests_directly()

    total   = summary.get("total_tests", 0)
    passed  = summary.get("passed", 0)
    failed  = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)
    status  = "PASS" if failed == 0 else "FAIL"

    report_lines = [
        "WAI Integration Test Report",
        "=" * 60,
        f"Mode:    {args.mode}",
        f"Status:  {status}",
        "",
        "Summary:",
        f"  Total:   {total}",
        f"  Passed:  {passed}",
        f"  Failed:  {failed}",
        f"  Skipped: {skipped}",
        "",
        "Output:",
        "-" * 60,
        output,
    ]

    report = "\n".join(report_lines)
    Path(args.output).write_text(report)
    print(f"Report written to {args.output}")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
