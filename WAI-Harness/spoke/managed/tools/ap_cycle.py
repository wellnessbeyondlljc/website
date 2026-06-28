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
# A RED finish files a TRACKED triage lug here so a quarantined branch is never silently
# stranded (the no-dead-ends guarantee). review-type = human triage, AP never auto-runs it.
DEAD_END_LUG_DIR_REL = "WAI-Harness/spoke/local/lugs/bytype/review/open"


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
    """True if main can fast-forward to its upstream — i.e. main has NOT diverged (no
    local-only commits ahead of @{u}). No upstream configured -> local-only spoke, ff-ok.
    DIVERGED (local commits not in upstream) -> NOT ff-able: a cycle must never start on a
    diverged main, because pulling it would create a merge that is exactly how branches get
    stranded. (Up-to-date or behind both fast-forward cleanly, so they are ff-ok.)"""
    # main@{u}..main = commits on local main that are NOT in its upstream (local-only / ahead).
    r = _git(root, "rev-list", "--count", "main@{u}..main")
    if r.returncode != 0:
        return True  # no upstream configured -> local-only, treat as ff-ok
    try:
        ahead = int(r.stdout.strip())
    except ValueError:
        return True
    return ahead == 0


# ---------- pluggable verify/deploy gate ----------

def detect_verify_cmd(root: Path) -> Optional[List[str]]:
    """The platform verify/deploy gate: prefer the harness test suite. Returns a command
    list, or None when no suite is detectable (an unverifiable platform is NOT a pass)."""
    for rel in ("WAI-Harness/spoke/managed/tests", "tests"):
        if (root / rel).is_dir():
            return [sys.executable, "-m", "pytest", rel, "-q", "-p", "no:cacheprovider"]
    return None


def run_verify_gate(root: Path, cmd: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run the pluggable verify/deploy gate on the CURRENT platform (HEAD). unify-then-
    VERIFY, never -trust. Returns {ok, ran, status, detail}. A missing suite is reported
    ok=False/ran=False/status='no-tests' (HONEST: an unverifiable platform is not green)."""
    use = cmd or detect_verify_cmd(root)
    if not use:
        return {"ok": False, "ran": False, "status": "no-tests",
                "detail": "no verify suite detected — platform UNVERIFIED (not a pass)"}
    if isinstance(use, str):
        use = use.split()
    # Don't let the gate pollute the worktree: bytecode caches would otherwise show up as
    # untracked changes and make the very clean-check the gate feeds into read 'dirty'.
    import os
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run(use, cwd=str(root), capture_output=True, text=True, env=env)
    ok = r.returncode == 0
    tail = (r.stdout or r.stderr or "").splitlines()[-1:] or [""]
    return {"ok": ok, "ran": True, "status": "green" if ok else "RED",
            "returncode": r.returncode, "detail": tail[0][:200]}


# ---------- dead-end accountability (no silently-stranded branch) ----------

def dead_end_lug(branch: str, cycle: int, detail: str = "") -> Dict[str, Any]:
    """Pure: build the TRACKED triage lug recorded when a finish quarantines a RED branch."""
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (branch or "branch"))
    lug_id = f"review-ap-cycle-deadend-{safe}-v1"
    return {
        "id": lug_id, "lug_id": lug_id, "type": "review", "status": "open",
        "schema_version": 4, "urgency": 6, "impact": 6, "effort": "S", "effort_score": 2,
        "routed_to": "LOCAL", "authored_by": "ap_cycle",
        "title": (f"AP-cycle DEAD-END: cycle-{cycle} branch {branch} failed the verify gate "
                  f"(quarantined, NOT merged)"),
        "one_liner": ("A finished AP cycle failed its test/verify gate; its branch is retained "
                      "unmerged for triage instead of being silently stranded."),
        "summary": (f"ap_cycle finish quarantined {branch} (cycle {cycle}): the verify gate was RED, "
                    f"so the branch was NOT merged to main. Triage: fix-forward on the branch and re-run "
                    f"the gate, or explicitly retire it. Detail: {detail or 'gate failed'}"),
        "branch": branch, "cycle": cycle,
        "acceptance_criteria": [
            {"id": "AC1",
             "criterion": f"{branch} is either fixed-forward + merged green, or explicitly retired with a reason",
             "verification_test": f"`git branch --merged main` contains {branch}, OR the branch is deleted "
                                  f"with a recorded retire reason"},
        ],
        "file_targets": [branch],
    }


def file_dead_end_lug(root: Path, branch: str, cycle: int, detail: str = "") -> Dict[str, Any]:
    """Write the dead-end triage lug to disk (tracked). Best-effort — a write failure is
    reported, never raised, so it can't mask the quarantine it is recording."""
    lug = dead_end_lug(branch, cycle, detail)
    out_dir = root / DEAD_END_LUG_DIR_REL
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{lug['id']}.json"
        p.write_text(json.dumps(lug, indent=2))
        return {"filed": True, "path": str(p), "lug_id": lug["id"]}
    except OSError as e:
        return {"filed": False, "error": str(e), "lug_id": lug["id"]}


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
    ap.add_argument("--gate-passed", action="store_true",
                    help="finish: trust this as the test-gate result instead of running the gate")
    ap.add_argument("--verify-ok", action="store_true",
                    help="start: trust the platform verify gate as PASSED instead of running it")
    ap.add_argument("--verify-cmd", default=None,
                    help="pluggable verify/deploy gate command (default: auto-detect the harness test suite)")
    ap.add_argument("--execute", action="store_true", help="actually run git mutations (default: plan only)")
    args = ap.parse_args()
    root = Path(args.spoke).resolve()
    state = _load_state(root)

    if args.cmd == "status":
        br = state.get("branch")
        ahead = _commits_ahead(root, br) if br else 0
        print(json.dumps({**state, "commits_ahead": ahead}, indent=2))
        return

    vcmd = args.verify_cmd.split() if args.verify_cmd else None

    if args.cmd == "start":
        if args.verify_ok:
            verify = {"ok": True, "ran": False, "status": "override", "detail": "--verify-ok"}
        else:
            verify = run_verify_gate(root, vcmd)
        plan = plan_start(args.spoke_id, state, _main_clean(root), _main_ff(root), verify["ok"])
        plan["verify"] = verify
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
        if args.gate_passed:
            gate = {"ok": True, "ran": False, "status": "override", "detail": "--gate-passed"}
        else:
            gate = run_verify_gate(root, vcmd)
        plan = plan_finish(br, gate["ok"], _commits_ahead(root, br))
        plan["gate"] = gate
        if args.execute and plan["action"] in ("merge", "noop"):
            _run_steps(root, plan["steps"])
            _save_state(root, {"cycle": state.get("cycle"), "branch": None, "status": "idle"})
        elif args.execute and plan["action"] == "quarantine":
            dead = file_dead_end_lug(root, br, int(state.get("cycle") or 0), gate.get("detail", ""))
            plan["dead_end_lug"] = dead
            _save_state(root, {"cycle": state.get("cycle"), "branch": br, "status": "quarantined"})
        print(json.dumps(plan, indent=2))
        if plan["action"] == "quarantine":
            print("  QUARANTINED — RED gate; branch retained as a TRACKED dead-end (not merged)")
        return


if __name__ == "__main__":
    main()
