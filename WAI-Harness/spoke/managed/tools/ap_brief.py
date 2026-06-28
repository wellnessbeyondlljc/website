#!/usr/bin/env python3
"""ap_brief — the wheel's self-driving brief: one command, "what should this spoke do next?"

Composes the goal-driven-autopilot tools (all read-only) into a single recommendation:
  - CRITICAL PATH : the blocker to run first (unblocks the most downstream work)
  - PORTFOLIO     : the top aspirational initiative to concentrate budget on
  - BLOCK HANDLING: how many lugs are blocked and what % the ladder can re-route
This is the actionable synthesis of the whole P0-P5 + critical-path stack, per spoke.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import critical_path as cp  # noqa: E402
import portfolio as pf  # noqa: E402
import cross_spoke_eval as cse  # noqa: E402


def brief(root: str) -> dict:
    crit = cp.analyze(root)
    port = pf.rank_spoke(root, budget=8)
    drive = cse.eval_spoke(root)
    top_blocker = (crit.get("critical_blockers") or [{}])[0]
    recommendation = []
    if top_blocker.get("blocker") and top_blocker.get("dispatchable_now"):
        recommendation.append(
            f"RUN FIRST: {top_blocker['blocker']} (unblocks {top_blocker['total_unblocks']})")
    if port.get("chosen_initiative"):
        recommendation.append(f"CONCENTRATE ON: {port['chosen_initiative']}")
    if drive.get("blocked"):
        recommendation.append(
            f"BLOCKS: {drive['blocked']} blocked, {drive['drive_rate_pct']}% re-routable")
    else:
        recommendation.append("BLOCKS: none — pursue the top initiative directly (goal-starved, not blocked)")
    return {"spoke": crit.get("spoke"), "open_lugs": crit.get("open_lugs"),
            "top_blocker": top_blocker, "top_initiative": port.get("chosen_initiative"),
            "blocked": drive.get("blocked"), "drive_rate_pct": drive.get("drive_rate_pct"),
            "recommendation": recommendation}


def render(b: dict) -> str:
    out = [f"\n◆ AP BRIEF — {b['spoke']} ({b['open_lugs']} open lugs)"]
    for r in b["recommendation"]:
        out.append(f"   → {r}")
    return "\n".join(out)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ap_brief — per-spoke self-driving recommendation")
    ap.add_argument("--spokes", nargs="+", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    briefs = [brief(s) for s in args.spokes]
    if args.json:
        print(json.dumps(briefs, indent=2))
    else:
        for b in briefs:
            print(render(b))
