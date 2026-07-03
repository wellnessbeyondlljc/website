#!/usr/bin/env python3
"""portfolio — P4: Ozi as portfolio manager (health-floor, then top aspirational initiative).

The cross-spoke finding (s135): product spokes have flat, block-free backlogs — they don't
get stuck on blocks, they get stuck with no prioritized goal. This gives Ozi an initiative-
aware ranking: spend the MINIMUM to assure health, then concentrate the rest on the single
top-ranked aspirational initiative — instead of _sort_key's initiative-blind (urgency,-roi,wave).

Pure functions (unit-tested); CLI ranks a real spoke's open lugs. Wiring into
ozi_autopilot._sort_key is a thin follow-on (multiply roi by initiative_weight).
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RANK_TIER = {1: 3.0, 2: 2.0, 3: 1.5}
LIFECYCLE_FACTOR = {"dormant": 0.05, "complete": 0.0, "approved": 1.0,
                    "active": 1.0, "measuring": 1.0, "proposed": 0.5}


def initiative_weight(it: Optional[Dict[str, Any]]) -> float:
    if not it:
        return 1.0
    w = RANK_TIER.get(it.get("impact_rank"), 1.0)
    if it.get("focus_lock"):
        w *= 3.0
    w *= LIFECYCLE_FACTOR.get(it.get("lifecycle_state", "active"), 1.0)
    return round(w, 3)


def _flavor(it: Optional[Dict[str, Any]]) -> str:
    return (it or {}).get("flavor", "aspirational")


def top_aspirational(initiatives: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """The single highest-weight active aspirational initiative — gets the budget."""
    cand = [(iid, initiative_weight(it)) for iid, it in initiatives.items()
            if _flavor(it) == "aspirational"
            and it.get("lifecycle_state") not in ("dormant", "complete")]
    if not cand:
        return None
    return max(cand, key=lambda x: x[1])[0]


def allocate(lugs: List[Dict[str, Any]], initiatives: Dict[str, Dict[str, Any]],
             budget: int, health_floor_pct: int = 20) -> Dict[str, Any]:
    """Return an ordered dispatch plan: health up to the floor (cap), then the top
    aspirational initiative, then remaining aspirational by weight."""
    def iid_of(l):
        return l.get("initiative") or l.get("initiative_id")

    def w(l):
        return initiative_weight(initiatives.get(iid_of(l)))

    top = top_aspirational(initiatives)
    health = sorted([l for l in lugs if _flavor(initiatives.get(iid_of(l))) == "health"],
                    key=w, reverse=True)
    aspir = [l for l in lugs if _flavor(initiatives.get(iid_of(l))) != "health"]
    top_lugs = sorted([l for l in aspir if iid_of(l) == top], key=w, reverse=True)
    other = sorted([l for l in aspir if iid_of(l) != top], key=w, reverse=True)

    health_cap = math.ceil(budget * health_floor_pct / 100.0)
    plan, reasons = [], []
    for l in health[:health_cap]:
        plan.append(l); reasons.append("health-floor")
    for l in top_lugs:
        if len(plan) >= budget:
            break
        plan.append(l); reasons.append(f"top-aspirational:{top}")
    for l in other:
        if len(plan) >= budget:
            break
        plan.append(l); reasons.append("aspirational-overflow")
    return {"chosen_initiative": top, "health_cap": health_cap,
            "plan": [(_lid(l), r) for l, r in zip(plan, reasons)],
            "dispatched": len(plan), "budget": budget}


def _lid(l):
    return l.get("id") or l.get("lug_id") or "unknown"


# ---------- spoke IO (CLI) ----------

def _spoke_local(root):
    p = os.path.join(root, "WAI-Harness", "spoke", "local")
    return p if os.path.isdir(p) else None


def _load_initiatives(local) -> Dict[str, Dict[str, Any]]:
    p = os.path.join(local, "initiatives", "index.json")
    if not os.path.exists(p):
        return {}
    try:
        return {it["id"]: it for it in json.load(open(p)).get("initiatives", []) if it.get("id")}
    except (json.JSONDecodeError, OSError, KeyError):
        return {}


def _load_open_lugs(local):
    out = []
    for f in glob.glob(os.path.join(local, "lugs", "bytype", "*", "open", "*.json")):
        try:
            out.append(json.load(open(f)))
        except (json.JSONDecodeError, OSError):
            pass
    return out


def rank_spoke(root, budget=8, floor=20):
    local = _spoke_local(root)
    if not local:
        return {"spoke": root, "error": "no v4 spoke/local"}
    inits = _load_initiatives(local)
    lugs = _load_open_lugs(local)
    plan = allocate(lugs, inits, budget, floor)
    plan["spoke"] = os.path.basename(root.rstrip("/"))
    plan["open_lugs"] = len(lugs)
    plan["initiatives"] = len(inits)
    return plan


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="portfolio — initiative-aware dispatch ranking")
    ap.add_argument("--spoke", required=True)
    ap.add_argument("--budget", type=int, default=8)
    ap.add_argument("--floor", type=int, default=20)
    args = ap.parse_args()
    r = rank_spoke(args.spoke, args.budget, args.floor)
    print(json.dumps(r, indent=2))
