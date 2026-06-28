#!/usr/bin/env python3
"""critical_path — make AP smarter: find the blocker that unblocks the most work.

Replan re-routes AROUND a block. Critical-path goes the other way: when many lugs are
blocked_by a common dependency, the highest-leverage move is to DISPATCH that dependency
FIRST so the whole subtree unblocks next cycle. This computes, from the blocked_by graph,
the critical blockers ranked by how much downstream work each unblocks — a priority boost
signal AP/portfolio can act on.

Pure logic (unit-tested) + CLI over a real spoke. READ-ONLY.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def _lid(l):
    return l.get("id") or l.get("lug_id") or l.get("i") or "unknown"


def blocker_leverage(open_lugs: List[Dict[str, Any]], completed: set) -> List[Dict[str, Any]]:
    """Rank unresolved blockers by transitive downstream unblock count.

    A blocker that is itself an OPEN lug (dispatchable) and gates the most descendants
    is the highest-leverage thing to run next.
    """
    by_id = {_lid(l): l for l in open_lugs}
    # direct: blocker -> set of lugs directly blocked by it
    direct = defaultdict(set)
    for l in open_lugs:
        for b in (l.get("blocked_by") or []):
            if b not in completed:
                direct[b].add(_lid(l))

    # transitive closure: descendants unblocked if `blocker` completes
    def descendants(blocker, seen=None):
        seen = seen if seen is not None else set()
        for child in direct.get(blocker, ()):
            if child in seen:
                continue
            seen.add(child)
            descendants(child, seen)
        return seen

    rows = []
    for blocker in direct:
        dispatchable = blocker in by_id and not [
            b for b in (by_id[blocker].get("blocked_by") or []) if b not in completed
        ]
        rows.append({
            "blocker": blocker,
            "direct_unblocks": len(direct[blocker]),
            "total_unblocks": len(descendants(blocker)),
            "dispatchable_now": dispatchable,
        })
    # highest leverage first; dispatchable blockers win ties (they can run THIS cycle)
    rows.sort(key=lambda r: (r["dispatchable_now"], r["total_unblocks"], r["direct_unblocks"]), reverse=True)
    return rows


# ---------- spoke IO ----------

def _spoke_local(root):
    p = os.path.join(root, "WAI-Harness", "spoke", "local")
    return p if os.path.isdir(p) else None


def _open_lugs(local):
    out = []
    for st in ("open", "in_progress", "claimed"):
        for f in glob.glob(os.path.join(local, "lugs", "bytype", "*", st, "*.json")):
            try:
                out.append(json.load(open(f)))
            except (json.JSONDecodeError, OSError):
                pass
    return out


def _completed(local):
    ids = set()
    for st in ("completed", "done"):
        for f in glob.glob(os.path.join(local, "lugs", "bytype", "*", st, "*.json")):
            ids.add(Path(f).stem)
    return ids


def analyze(root) -> Dict[str, Any]:
    local = _spoke_local(root)
    if not local:
        return {"spoke": root, "error": "no v4 spoke/local"}
    lugs = _open_lugs(local)
    rows = blocker_leverage(lugs, _completed(local))
    return {"spoke": os.path.basename(root.rstrip("/")), "open_lugs": len(lugs),
            "critical_blockers": rows[:10]}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="critical_path — highest-leverage blocker to run next")
    ap.add_argument("--spoke", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = analyze(args.spoke)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"\n{r.get('spoke')}  ({r.get('open_lugs')} open)  — critical blockers (run these first):")
        for b in r.get("critical_blockers", []):
            tag = "DISPATCHABLE NOW" if b["dispatchable_now"] else "itself blocked"
            print(f"  {b['total_unblocks']:>3} unblocked  [{tag:<16}]  {b['blocker']}")
