#!/usr/bin/env python3
"""deliver_goal — deliver an operator-set wheel_goal to a spoke's incoming/ as a v4 lug
and record it in the hub fleet-goals ledger. The sovereign cross-spoke channel for the
s135 goal-definition campaign (mywheel never edits another spoke's state directly).

Usage:
  python3 deliver_goal.py --spoke-path /p --spoke-id name --goal goal.json [--hub-root .] [--local]
goal.json = {north_star, top_focus|ordered_focus, success_criteria{...}, health_floor[...], notes?}
--local: the spoke is mywheel itself -> write wheel_goal straight into its index (no lug).
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def _lug(spoke_id, goal):
    return {
        "created_at": "2026-06-26T08:45:00Z", "created_by": "mywheel-session-20260626-0117",
        "fw_version": "4.3.1", "gb": "claude-opus-4-8", "status": "open", "va": "adopt",
        "routed_to": f"SPOKE/{spoke_id}", "initiative": "wheel-goal-adoption",
        "id": f"task-adopt-wheel-goal-{spoke_id}-v1", "lug_id": f"task-adopt-wheel-goal-{spoke_id}-v1",
        "type": "task", "schema_version": 4, "rev": 1, "urgency": 3, "impact": 7,
        "effort": "S", "effort_score": 2, "model_fit": "sonnet",
        "title": f"Adopt operator-set wheel_goal for {spoke_id}",
        "one_liner": "Operator set this spoke's goal in the s135 fleet goal-definition campaign; adopt it into the index.",
        "summary": "Adopt the wheel_goal_payload into this spoke's initiatives/index.json (measured-goal design): set north_star, the top/ordered focus, success_criteria, and health_floor; re-rank initiatives to match the focus. Delivered via incoming/ so the spoke adopts its own goal (cross-spoke sovereignty).",
        "situation": f"{spoke_id} had no operator-set measured top goal AP could roll toward (goal-starved). Operator provided it directly in the s135 campaign.",
        "context_snapshot": "s135 mywheel-driven fleet goal-definition campaign over core+active spokes.",
        "triggering_session": "session-20260626-0117 (s135) mywheel; operator-provided goal",
        "decision_rationale": "Deliver via incoming/ lug (sovereign channel) so the spoke adopts its own goal rather than mywheel editing its source.",
        "alternatives_considered": "mywheel edits the spoke directly (rejected: cross-spoke sovereignty); leave goal-starved (rejected: defeats the campaign).",
        "wheel_goal_payload": goal,
        "pev": {
            "perceive": ["Read this spoke's initiatives/index.json + WAI-State _project_foundation"],
            "execute": ["Add wheel_goal_payload as wheel_goal in the index", "Re-rank initiatives to match the focus", "Set focus_lock on the single top aspirational initiative"],
            "verify": ["index has wheel_goal with success_criteria + health_floor", "top initiative matches the stated focus"]},
        "acceptance_criteria": [
            {"id": "AC1", "criterion": "wheel_goal adopted into the index with success_criteria + health_floor", "verification_test": "grep wheel_goal in index"},
            {"id": "AC2", "criterion": "initiatives re-ranked so the top focus is rank-1 aspirational focus_lock", "verification_test": "index rank/flavor order"}],
        "target_files": ["WAI-Harness/spoke/local/initiatives/index.json"],
        "verification_test": [
            {"mode": "mechanical", "covers_ac": "AC1", "check_ref": "grep wheel_goal index", "result": None},
            {"mode": "mechanical", "covers_ac": "AC2", "check_ref": "index rank order", "result": None}],
        "bolt_ref": None, "updated_at": "2026-06-26",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spoke-path", required=True)
    ap.add_argument("--spoke-id", required=True)
    ap.add_argument("--goal", required=True, help="path to goal.json")
    ap.add_argument("--hub-root", default=".")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()
    goal = json.load(open(args.goal))

    if args.local:
        idxp = os.path.join(args.spoke_path, "WAI-Harness/spoke/local/initiatives/index.json")
        idx = json.load(open(idxp))
        idx[f"wheel_goal_{args.spoke_id}"] = goal
        json.dump(idx, open(idxp, "w"), indent=2, ensure_ascii=False)
        dest = idxp
    else:
        inc = os.path.join(args.spoke_path, "WAI-Harness/spoke/local/lugs/incoming")
        os.makedirs(inc, exist_ok=True)
        dest = os.path.join(inc, f"task-adopt-wheel-goal-{args.spoke_id}-v1.json")
        json.dump(_lug(args.spoke_id, goal), open(dest, "w"), indent=2, ensure_ascii=False)
        r = subprocess.run([sys.executable, str(TOOLS / "validate_lug_v4.py"), dest],
                           capture_output=True, text=True)
        if "OK" not in r.stdout:
            print("LUG INVALID:", r.stdout, r.stderr); return 1

    # ledger
    led = os.path.join(args.hub_root, "WAI-Harness/hub/local/fleet-goals.json")
    d = json.load(open(led)) if os.path.exists(led) else {"schema": "fleet-goals-v1", "spokes": {}}
    d.setdefault("spokes", {})[args.spoke_id] = {
        "north_star": goal.get("north_star"),
        "focus": goal.get("ordered_focus") or goal.get("top_focus"),
        "success_metric": (goal.get("success_criteria") or {}).get("target"),
        "health_floor": [h.get("name") if isinstance(h, dict) else h for h in (goal.get("health_floor") or [])],
        "status": "set-local" if args.local else "delivered-to-incoming"}
    d["updated_at"] = "2026-06-26"
    json.dump(d, open(led, "w"), indent=2, ensure_ascii=False)
    print(f"  {'set-local' if args.local else 'delivered'}: {dest}")
    print(f"  ledger: {args.spoke_id} recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
