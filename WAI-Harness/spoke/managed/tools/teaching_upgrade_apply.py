#!/usr/bin/env python3
"""Spoke upgrade executor — verify-apply-verify loop for consolidated upgrade teachings.

Per spec-teaching-delivery-system-v1 use_cases[3]:
  For each teaching in a consolidated upgrade teaching:
    1. Run verification_steps — all pass -> SKIP (already applied)
    2. Any fail -> run apply_steps -> re-run verification_steps
    3. All pass after apply -> ACCEPTED
    4. Still fail -> log to upgrade-failures.jsonl, continue

CLI:
  python3 tools/teaching_upgrade_apply.py apply \\
      --spoke-path <path> --teaching <consolidated.json> [--dry-run]
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASHER_SENTINEL = ".basher-managed"
UPGRADE_FAILURES_FILE = "WAI-Spoke/teachings/upgrade-failures.jsonl"
BASE_VERSION_FILE = "WAI-Spoke/base_version"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Check executors
# ---------------------------------------------------------------------------

def _run_shell(cmd: str, cwd: Path) -> tuple[bool, str]:
    """Run a shell command; return (passed, output)."""
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=str(cwd),
            capture_output=True, text=True, timeout=30
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


def _run_check(step: dict[str, Any], spoke: Path) -> tuple[bool, str]:
    """Execute one verification_step check. Returns (passed, detail)."""
    check = step.get("check", "").strip()

    if check.startswith("file_exists:"):
        target = Path(check.split(":", 1)[1].strip())
        if not target.is_absolute():
            target = spoke / target
        ok = target.exists()
        return ok, str(target)

    if check.startswith("json_field:"):
        # json_field: <file> <key> <expected_value>
        parts = check.split(":", 1)[1].strip().split()
        if len(parts) < 3:
            return False, f"malformed json_field check: {check!r}"
        fpath = spoke / parts[0]
        key, expected = parts[1], " ".join(parts[2:])
        try:
            data = json.loads(fpath.read_text())
            actual = str(data.get(key, ""))
            return actual == expected, f"{key}={actual!r} (expected {expected!r})"
        except (OSError, json.JSONDecodeError) as e:
            return False, str(e)

    if check.startswith("grep:"):
        # grep: <pattern> <file>
        parts = check.split(":", 1)[1].strip().split(None, 1)
        if len(parts) < 2:
            return False, f"malformed grep check: {check!r}"
        pattern, fpath = parts[0], parts[1]
        return _run_shell(f"grep -q {pattern} {fpath}", spoke)

    # Default: treat as shell command
    return _run_shell(check, spoke)


def _run_apply_step(step: dict[str, Any], spoke: Path) -> tuple[bool, str]:
    """Execute one apply_step action. Returns (ok, output)."""
    action = step.get("action", "").strip()
    return _run_shell(action, spoke)


def _is_basher_managed(action: str, spoke: Path) -> bool:
    """Check if an action targets a Basher-managed directory."""
    # Extract first path-like token from the action
    for token in action.split():
        candidate = Path(token) if token.startswith("/") else spoke / token
        # Walk up to find a .basher-managed sentinel
        check_path = candidate if candidate.is_dir() else candidate.parent
        while True:
            if (check_path / BASHER_SENTINEL).exists():
                return True
            parent = check_path.parent
            if parent == check_path:
                break
            check_path = parent
    return False


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _run_verification(steps: list[dict], spoke: Path) -> tuple[bool, list[dict]]:
    """Run all verification steps. Returns (all_passed, results)."""
    results = []
    all_passed = True
    for step in steps:
        passed, detail = _run_check(step, spoke)
        results.append({"id": step.get("id"), "passed": passed, "detail": detail})
        if not passed:
            all_passed = False
    return all_passed, results


def apply_upgrade(
    spoke_path: Path,
    teaching_path: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply a consolidated upgrade teaching to a spoke. Returns summary dict."""
    if not spoke_path.exists():
        return {"ok": False, "error": f"spoke path not found: {spoke_path}"}

    try:
        consolidated = json.loads(teaching_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": f"could not load teaching: {e}"}

    if consolidated.get("type") != "consolidated":
        return {"ok": False, "error": f"expected type=consolidated, got {consolidated.get('type')!r}"}

    base_version = consolidated.get("base_version", "")
    teachings = consolidated.get("teachings", [])

    # Ensure spoke teachings dir exists
    teachings_dir = spoke_path / "WAI-Spoke" / "teachings"
    if not dry_run:
        teachings_dir.mkdir(parents=True, exist_ok=True)

    outcomes = []
    failures = []

    for entry in teachings:
        tid = entry.get("id", "unknown")
        vsteps = entry.get("verification_steps", [])
        asteps = entry.get("apply_steps", [])

        # Step 1: pre-check
        pre_passed, pre_results = _run_verification(vsteps, spoke_path)

        if pre_passed:
            outcomes.append({"id": tid, "outcome": "SKIP", "reason": "verification already passes"})
            continue

        if dry_run:
            outcomes.append({"id": tid, "outcome": "WOULD_APPLY", "pre_check": pre_results})
            continue

        # Step 2: apply
        apply_ok = True
        apply_log = []
        for step in asteps:
            action = step.get("action", "")
            if _is_basher_managed(action, spoke_path):
                apply_log.append({
                    "id": step.get("id"),
                    "skipped": True,
                    "reason": "basher-managed path"
                })
                continue
            ok, out = _run_apply_step(step, spoke_path)
            apply_log.append({"id": step.get("id"), "ok": ok, "output": out})
            if not ok:
                apply_ok = False
                break

        if not apply_ok:
            record = {
                "id": tid,
                "outcome": "FAILED",
                "reason": "apply_step failed",
                "apply_log": apply_log,
                "failed_at": _now(),
            }
            outcomes.append(record)
            failures.append(record)
            continue

        # Step 3: re-verify
        post_passed, post_results = _run_verification(vsteps, spoke_path)
        if post_passed:
            outcomes.append({
                "id": tid,
                "outcome": "ACCEPTED",
                "apply_log": apply_log,
                "post_check": post_results,
            })
        else:
            record = {
                "id": tid,
                "outcome": "FAILED",
                "reason": "verification failed after apply",
                "apply_log": apply_log,
                "post_check": post_results,
                "failed_at": _now(),
            }
            outcomes.append(record)
            failures.append(record)

    # Write failure log
    if failures and not dry_run:
        failures_path = spoke_path / UPGRADE_FAILURES_FILE
        failures_path.parent.mkdir(parents=True, exist_ok=True)
        with failures_path.open("a") as fh:
            for f in failures:
                fh.write(json.dumps(f) + "\n")

    # Update base_version if no failures
    version_written = False
    if not failures and not dry_run and base_version:
        bv_path = spoke_path / BASE_VERSION_FILE
        bv_path.parent.mkdir(parents=True, exist_ok=True)
        bv_path.write_text(base_version + "\n")
        version_written = True

    return {
        "ok": True,
        "dry_run": dry_run,
        "base_version": base_version,
        "version_written": version_written,
        "outcomes": outcomes,
        "failure_count": len(failures),
    }


def _main(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Teaching upgrade executor")
    sub = p.add_subparsers(dest="cmd", required=True)

    apply_p = sub.add_parser("apply")
    apply_p.add_argument("--spoke-path", required=True)
    apply_p.add_argument("--teaching", required=True)
    apply_p.add_argument("--dry-run", action="store_true")

    args = p.parse_args(argv)

    if args.cmd == "apply":
        result = apply_upgrade(
            Path(args.spoke_path),
            Path(args.teaching),
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
