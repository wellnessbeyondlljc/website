#!/usr/bin/env python3
"""cross_spoke_eval — test the goal-driven loop against OTHER spokes' real backlogs.

READ-ONLY on the source spoke: it reads a spoke's lugs, finds the genuinely-blocked
ones, and runs the replan ladder against them into an ISOLATED tmp store (never touches
the source spoke's state). Reports per-spoke drive rate so we can see whether the wheel
generalizes — and surface bugs from diverse real backlogs.

Run: python3 cross_spoke_eval.py --spokes /path/a /path/b ...
"""
from __future__ import annotations

import glob
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import goal_planner as gp  # noqa: E402


def _spoke_local(root: str) -> Optional[str]:
    p = os.path.join(root, "WAI-Harness", "spoke", "local")
    return p if os.path.isdir(p) else None


def _load_lugs(local: str, statuses=("open", "in_progress", "claimed")) -> List[Dict[str, Any]]:
    out = []
    for st in statuses:
        for f in glob.glob(os.path.join(local, "lugs", "bytype", "*", st, "*.json")):
            try:
                d = json.load(open(f))
                d["_fs_status"] = st
                out.append(d)
            except (json.JSONDecodeError, OSError):
                pass
    return out


def _completed_ids(local: str) -> set:
    ids = set()
    for st in ("completed", "done"):
        for f in glob.glob(os.path.join(local, "lugs", "bytype", "*", st, "*.json")):
            ids.add(Path(f).stem)
    return ids


def _lid(l):
    return l.get("id") or l.get("lug_id") or l.get("i") or "unknown"


def _blocked(l, completed: set):
    """Return (block_class, reason) for any block type, else None.

    Detects all the static block signatures (not just blocked_by): dependency blocks,
    execute_when gates, and stall candidates (prior autopilot failures).
    """
    bb = l.get("blocked_by") or []
    unresolved = [b for b in bb if b not in completed]
    if unresolved:
        return ("blocked_by", f"blocked: {', '.join(map(str, unresolved[:2]))}")
    ew = l.get("execute_when") or {}
    if ew:
        if ew.get("manual_gate"):
            return ("execute_when", "manual gate")
        ac = [x for x in (ew.get("all_completed") or []) if x not in completed]
        if ac:
            return ("execute_when", f"all_completed unmet: {', '.join(map(str, ac[:2]))}")
    if int((l.get("workflow") or {}).get("autopilot_failures", 0)) >= 2:
        return ("stall", f"{l['workflow']['autopilot_failures']} prior failures")
    return None


def eval_spoke(root: str) -> Dict[str, Any]:
    local = _spoke_local(root)
    if not local:
        return {"spoke": root, "error": "no v4 spoke/local"}
    lugs = _load_lugs(local)
    completed = _completed_ids(local)
    open_ids = {_lid(l): l for l in lugs}
    tmp = tempfile.mkdtemp()
    (Path(tmp) / "WAI-Harness" / "spoke" / "local" / "capabilitygraph").mkdir(parents=True)

    def sibling_lookup(l):
        gid = l.get("goal_id")
        init = l.get("initiative") or l.get("initiative_id")
        for oid, o in open_ids.items():
            if oid == _lid(l) or (o.get("blocked_by") or []):
                continue
            if (gid and o.get("goal_id") == gid) or (init and (o.get("initiative") or o.get("initiative_id")) == init):
                return oid
        return None

    subbed = esc = blocked_n = 0
    errors = 0
    by_class: Dict[str, int] = {}
    for l in lugs:
        blk = _blocked(l, completed)
        if not blk:
            continue
        bclass, reason = blk
        blocked_n += 1
        by_class[bclass] = by_class.get(bclass, 0) + 1
        try:
            r = gp.replan_on_block(l, bclass, reason, ctx=gp.new_ctx(),
                                   spoke_local=tmp, sibling_lookup=sibling_lookup)
            if r["action"] == "substitute":
                subbed += 1
            else:
                esc += 1
        except Exception as e:
            errors += 1
            print(f"  [cross_spoke_eval] ERROR on {_lid(l)} @ {root}: {e}", file=sys.stderr)
    dr = round(100.0 * subbed / blocked_n, 1) if blocked_n else 0.0
    return {"spoke": os.path.basename(root.rstrip("/")), "open_lugs": len(lugs),
            "blocked": blocked_n, "substituted": subbed, "escalated": esc,
            "drive_rate_pct": dr, "errors": errors, "by_class": by_class}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--spokes", nargs="+", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = [eval_spoke(s) for s in args.spokes]
    if args.json:
        print(json.dumps(rows, indent=2)); return
    print(f"\n{'spoke':<26}{'open':>6}{'blocked':>9}{'subst':>7}{'esc':>6}{'drive%':>8}{'err':>5}")
    print("-" * 67)
    tot = {"open_lugs": 0, "blocked": 0, "substituted": 0, "escalated": 0, "errors": 0}
    for r in rows:
        if r.get("error"):
            print(f"{r['spoke'][:25]:<26}  {r['error']}"); continue
        print(f"{r['spoke'][:25]:<26}{r['open_lugs']:>6}{r['blocked']:>9}{r['substituted']:>7}{r['escalated']:>6}{r['drive_rate_pct']:>7}%{r['errors']:>5}")
        for k in tot:
            tot[k] += r.get(k, 0)
    fdr = round(100.0 * tot["substituted"] / tot["blocked"], 1) if tot["blocked"] else 0.0
    print("-" * 67)
    print(f"{'FLEET':<26}{tot['open_lugs']:>6}{tot['blocked']:>9}{tot['substituted']:>7}{tot['escalated']:>6}{fdr:>7}%{tot['errors']:>5}")


if __name__ == "__main__":
    main()
