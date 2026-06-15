#!/usr/bin/env python3
"""
Pre-commit health gate for WAI spokes.

Runs a quick health check and exits non-zero if critical drift is detected.
Designed to be fast (<100ms) and catch only FAIL-level findings.

Also runs security_scan on changed prompt/teaching files to catch injection patterns.

Usage:
  python3 tools/pre_commit_health.py          # check current dir
  python3 tools/pre_commit_health.py /path     # check specific spoke

Exit codes:
  0 = healthy (or no WAI-Spoke found — not a WAI project)
  1 = drift detected — fix before committing
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.spoke_health_check import run_health_check


def run_security_scan(spoke_path):
    """Run security_scan on prompt surfaces within the spoke."""
    from tools.security_scan import load_patterns, scan_target, scan_file

    patterns = load_patterns()
    findings = []

    # Scan advisor context_prompt.md files
    advisors_dir = Path(spoke_path) / "WAI-Spoke" / "advisors"
    if advisors_dir.exists():
        findings.extend(scan_target(str(advisors_dir), patterns))

    # Scan teachings in hub directory
    hub_teachings = Path(spoke_path) / "hub" / "teachings_repo"
    if hub_teachings.exists():
        findings.extend(scan_target(str(hub_teachings), patterns))

    # Scan open lug files for _behavior_directive
    lugs_dir = Path(spoke_path) / "WAI-Spoke" / "lugs" / "bytype"
    if lugs_dir.exists():
        findings.extend(scan_target(str(lugs_dir), patterns))

    block_findings = [f for f in findings if f.get("severity") == "block"]
    warn_findings = [f for f in findings if f.get("severity") == "warn"]

    if warn_findings:
        print(f"WAI security scan: {len(warn_findings)} warning(s) found")
        for w in warn_findings:
            print(f"  WARN: {w.get('file', '?')} — {w.get('message', '?')}")

    if block_findings:
        print(f"WAI security scan: {len(block_findings)} block-level finding(s)")
        for b in block_findings:
            print(f"  BLOCK: {b.get('file', '?')} — {b.get('message', '?')}")
        return False  # unhealthy

    return True  # healthy (warnings are OK for warn-only policy)


def main():
    parser = argparse.ArgumentParser(description="Pre-commit spoke health check.")
    parser.add_argument("--spoke-path", default=".", metavar="PATH", help="Path to spoke root")
    args = parser.parse_args()
    spoke_path = args.spoke_path

    # Skip silently if not a WAI project
    wai_spoke = Path(spoke_path) / "WAI-Spoke"
    if not wai_spoke.exists():
        sys.exit(0)

    # Run structural health check
    report = run_health_check(spoke_path, mode="quick")

    if report.failed > 0:
        print(f"WAI pre-commit: {report.failed} issue(s) found")
        for c in report.checks:
            if c.status == "FAIL":
                print(f"  FAIL: {c.id} — {c.detail}")
        print("Fix these before committing. Run: python3 tools/spoke_health_check.py . --quick")
        sys.exit(1)

    # Run security scan on prompt surfaces
    if not run_security_scan(spoke_path):
        sys.exit(1)

    # Healthy — exit silently for clean pre-commit experience
    sys.exit(0)


if __name__ == "__main__":
    main()
