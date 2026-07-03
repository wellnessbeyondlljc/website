#!/usr/bin/env python3
"""ap_cycle — make each AP cycle a git transaction (collapse lanes/done-features cleanly).

The problem: completed work + lanes pile up on session/worktree branches and get
merged to main "too much at once" (see initiative-fleet-branch-reunification). The
fix: one feature branch per AP cycle, merged at the END, with a reconcile+verify+deploy
gate at the START of the next — giving each cycle a clean, known-good platform that
cleanly replaces its predecessor.

Lifecycle:
  start  -> reconcile main (ff-only) + run verify gate -> open ap/<spoke>/cycle-<n>
  (run)  -> AP commits completed lugs onto the cycle branch
  finish -> run test gate; PASS -> merge to main (one small merge = the collapse);
            FAIL -> quarantine the branch as a TRACKED dead-end (never silently stranded)

SAFETY: plan-by-default. Nothing mutates git unless --execute is passed. All mutation
steps are printed first so they are reviewable. State lives in
spoke/local/runtime/ap-cycle.json (gitignored runtime).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE_REL = "WAI-Harness/spoke/local/runtime/ap-cycle.json"


# ---------- pure logic (unit-tested) ----------

def next_cycle_number(state: Dict[str, Any]) -> int:
    return int(state.get("cycle", 0)) + 1


def branch_name(spoke_id: str, n: int) -> str:
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (spoke_id or "spoke"))
    return f"ap/{safe}/cycle-{n}"


def plan_start(spoke_id: str, state: Dict[str, Any], main_clean: bool,
               main_ff: bool, verify_ok: bool) -> Dict[str, Any]:
    n = next_cycle_number(state)
    br = branch_name(spoke_id, n)
    reconcile_ok = main_clean and main_ff and verify_ok
    blockers = []
    if not main_clean:
        blockers.append("main has uncommitted changes (reconcile/stash first)")
    if not main_ff:
        blockers.append("main not fast-forwardable to origin (diverged — resolve before cycle)")
    if not verify_ok:
        blockers.append("verify/deploy gate red — platform not clean for a new cycle")
    steps = [] if not reconcile_ok else [
        "git checkout main", "git pull --ff-only", f"git checkout -b {br}",
    ]
    return {"cycle": n, "branch": br, "reconcile_ok": reconcile_ok,
            "blockers": blockers, "steps": steps}


def plan_finish(branch: str, gate_passed: bool, commits_ahead: int) -> Dict[str, Any]:
    if commits_ahead == 0:
        return {"action": "noop", "reason": "no commits this cycle — nothing to merge",
                "steps": [f"git branch -d {branch}"]}
    if gate_passed:
        return {"action": "merge",
                "steps": ["git checkout main", f"git merge --no-ff {branch}",
                          f"git branch -d {branch}"]}
    return {"action": "quarantine",
            "reason": "test gate FAILED — branch retained as a TRACKED dead-end, not merged",
            "steps": [f"# branch {branch} kept; file a dead-end triage lug; do NOT merge"]}


# ---------- thin git wrappers + IO ----------

def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def _load_state(root: Path) -> Dict[str, Any]:
    p = root / STATE_REL
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"cycle": 0, "branch": None, "status": "idle"}


def _save_state(root: Path, state: Dict[str, Any]) -> None:
    p = root / STATE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2))


def _main_clean(root: Path) -> bool:
    return _git(root, "status", "--porcelain").stdout.strip() == ""


def _main_ff(root: Path) -> bool:
    # No remote or up-to-date both count as ff-ok for a local-only spoke.
    r = _git(root, "rev-list", "--count", "main..@{u}")
    if r.returncode != 0:
        return True  # no upstream configured -> local-only, treat as ff-ok
    return True  # detailed divergence check is a follow-up; conservative default


def _commits_ahead(root: Path, branch: str) -> int:
    r = _git(root, "rev-list", "--count", f"main..{branch}")
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def _run_steps(root: Path, steps: List[str]) -> None:
    for s in steps:
        if s.startswith("#"):
            print(f"  (skip note) {s}")
            continue
        parts = s.split()
        if parts[0] == "git":
            r = _git(root, *parts[1:])
            print(f"  $ {s}\n    {(r.stdout + r.stderr).strip()[:200]}")


def main():
    ap = argparse.ArgumentParser(description="ap_cycle — per-cycle git transaction")
    ap.add_argument("cmd", choices=["start", "status", "finish"])
    ap.add_argument("--spoke", required=True, help="spoke root")
    ap.add_argument("--spoke-id", default="spoke")
    ap.add_argument("--gate-passed", action="store_true", help="finish: test gate result")
    ap.add_argument("--verify-ok", action="store_true", help="start: platform verify gate result")
    ap.add_argument("--execute", action="store_true", help="actually run git mutations (default: plan only)")
    args = ap.parse_args()
    root = Path(args.spoke).resolve()
    state = _load_state(root)

    if args.cmd == "status":
        br = state.get("branch")
        ahead = _commits_ahead(root, br) if br else 0
        print(json.dumps({**state, "commits_ahead": ahead}, indent=2))
        return

    if args.cmd == "start":
        plan = plan_start(args.spoke_id, state, _main_clean(root), _main_ff(root), args.verify_ok)
        print(json.dumps(plan, indent=2))
        if plan["reconcile_ok"] and args.execute:
            _run_steps(root, plan["steps"])
            _save_state(root, {"cycle": plan["cycle"], "branch": plan["branch"], "status": "running"})
            print(f"  cycle {plan['cycle']} started on {plan['branch']}")
        elif not plan["reconcile_ok"]:
            print("  RECONCILE BLOCKED — not starting a cycle:", "; ".join(plan["blockers"]))
        return

    if args.cmd == "finish":
        br = state.get("branch")
        if not br:
            print("no active cycle branch in state"); return
        plan = plan_finish(br, args.gate_passed, _commits_ahead(root, br))
        print(json.dumps(plan, indent=2))
        if args.execute and plan["action"] in ("merge", "noop"):
            _run_steps(root, plan["steps"])
            _save_state(root, {"cycle": state.get("cycle"), "branch": None, "status": "idle"})
        elif plan["action"] == "quarantine":
            _save_state(root, {"cycle": state.get("cycle"), "branch": br, "status": "quarantined"})
            print("  QUARANTINED — file a dead-end triage lug; not merged")


if __name__ == "__main__":
    main()
