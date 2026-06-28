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
# Lifecycle states whose lugs are treated as weight ~0 — never dispatched.
INERT_STATES = ("dormant", "complete")
# Policy defaults (overridable via spec-initiative-priority-v1.json config block).
DEFAULT_HEALTH_FLOOR_PCT = 20      # reserve UP TO this % of the budget for health (a CAP)
DEFAULT_CONCENTRATION_MAX_PCT = 70  # one aspirational initiative may take AT MOST this % of the budget


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


def _iid_of(l: Dict[str, Any]) -> Optional[str]:
    return l.get("initiative") or l.get("initiative_id")


def _is_dispatchable(it: Optional[Dict[str, Any]]) -> bool:
    """A lug is inert (never dispatched) iff its initiative is dormant/complete.
    Lugs with no initiative (it is None) are dispatchable — they are not inert."""
    return (it or {}).get("lifecycle_state") not in INERT_STATES


def _ordered_plan(lugs: List[Dict[str, Any]], initiatives: Dict[str, Dict[str, Any]],
                  budget: int, health_floor_pct: int = DEFAULT_HEALTH_FLOOR_PCT,
                  concentration_max_pct: int = DEFAULT_CONCENTRATION_MAX_PCT
                  ) -> List[Tuple[Dict[str, Any], str]]:
    """Full portfolio dispatch order (NOT trimmed to budget — the caller's budget
    gate trims). Order:
      1. health, up to the health-floor cap (the reservation — a CAP, not a floor)
      2. the single top aspirational initiative, up to the concentration cap
      3. all other aspirational work (so no one initiative starves the rest)
      4. top-aspirational overflow (concentrate leftover budget, don't waste it)
      5. health overflow (only after aspirational work is exhausted)
    Lugs tied to a dormant/complete initiative are excluded entirely (weight ~0).
    """
    def w(l):
        return initiative_weight(initiatives.get(_iid_of(l)))

    live = [l for l in lugs if _is_dispatchable(initiatives.get(_iid_of(l)))]
    top = top_aspirational(initiatives)
    health = sorted([l for l in live if _flavor(initiatives.get(_iid_of(l))) == "health"],
                    key=w, reverse=True)
    aspir = [l for l in live if _flavor(initiatives.get(_iid_of(l))) != "health"]
    top_lugs = sorted([l for l in aspir if _iid_of(l) == top], key=w, reverse=True)
    other = sorted([l for l in aspir if _iid_of(l) != top], key=w, reverse=True)

    health_cap = math.ceil(budget * health_floor_pct / 100.0) if budget > 0 else 0
    conc_cap = math.ceil(budget * concentration_max_pct / 100.0) if budget > 0 else 0

    plan: List[Tuple[Dict[str, Any], str]] = []
    plan += [(l, "health-floor") for l in health[:health_cap]]
    plan += [(l, f"top-aspirational:{top}") for l in top_lugs[:conc_cap]]
    plan += [(l, "aspirational-other") for l in other]
    plan += [(l, "top-aspirational-overflow") for l in top_lugs[conc_cap:]]
    plan += [(l, "health-overflow") for l in health[health_cap:]]
    return plan


def reorder_for_dispatch(lugs: List[Dict[str, Any]], initiatives: Dict[str, Dict[str, Any]],
                         budget: int, health_floor_pct: int = DEFAULT_HEALTH_FLOOR_PCT,
                         concentration_max_pct: int = DEFAULT_CONCENTRATION_MAX_PCT
                         ) -> List[Dict[str, Any]]:
    """Reorder open lugs for portfolio dispatch (returns lug objects, untrimmed).

    The caller iterates and stops at its own budget gate; this only decides the
    ORDER (health-floor first, then concentrate on the top aspirational initiative)
    and DROPS dormant/complete-initiative lugs. Pure — never reads disk."""
    return [l for l, _ in _ordered_plan(lugs, initiatives, budget,
                                        health_floor_pct, concentration_max_pct)]


def allocate(lugs: List[Dict[str, Any]], initiatives: Dict[str, Dict[str, Any]],
             budget: int, health_floor_pct: int = DEFAULT_HEALTH_FLOOR_PCT,
             concentration_max_pct: int = DEFAULT_CONCENTRATION_MAX_PCT) -> Dict[str, Any]:
    """Return an ordered dispatch plan trimmed to budget: health up to the floor
    (cap), then the single top aspirational initiative (bounded by the concentration
    max), then other aspirational, then overflow."""
    plan = _ordered_plan(lugs, initiatives, budget, health_floor_pct,
                         concentration_max_pct)[: max(budget, 0)]
    health_cap = math.ceil(budget * health_floor_pct / 100.0) if budget > 0 else 0
    conc_cap = math.ceil(budget * concentration_max_pct / 100.0) if budget > 0 else 0
    return {"chosen_initiative": top_aspirational(initiatives),
            "health_cap": health_cap, "concentration_cap": conc_cap,
            "plan": [(_lid(l), r) for l, r in plan],
            "dispatched": len(plan), "budget": budget}


def load_policy(spec_path: Optional[str] = None) -> Tuple[int, int]:
    """Read (health_floor_pct, concentration_max_pct) from the initiative-priority
    spec config block. Fail-open to the module defaults if the spec is absent/bad."""
    floor, conc = DEFAULT_HEALTH_FLOOR_PCT, DEFAULT_CONCENTRATION_MAX_PCT
    try:
        if spec_path is None:
            spec_path = (Path(__file__).resolve().parent.parent / "knowledge" /
                         "spec" / "open" / "spec-initiative-priority-v1.json")
        cfg = json.loads(Path(spec_path).read_text()).get("config", {})
        floor = int(cfg.get("health_floor_pct", floor))
        conc = int(cfg.get("concentration_max_pct", conc))
    except Exception:
        pass
    return floor, conc


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
