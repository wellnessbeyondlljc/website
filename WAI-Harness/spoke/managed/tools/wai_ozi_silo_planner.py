#!/usr/bin/env python3
"""Flight Control Optimizer — conflict graph + heat map + Ozi attack plan.

Reads the open lug backlog, builds the conflict graph (sub-graph of PathGraph),
identifies silos (connected components), computes heat, detects pioneers,
runs the hot spot review gate, assigns execution modes, and emits an attack
plan for concurrent autopilot dispatch.

Usage:
    python3 wai_ozi_silo_planner.py [--output-dir PATH] [--quiet] [--json]
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Resolve the spoke's working-state base v4/v3-aware via wai_paths (the single source
# of truth), matching ozi_autopilot/wai_ozi_config. The old constants hardcoded a v3
# WAI-Spoke path relative to this tool's dir, so a v4-only spoke (no WAI-Spoke tree)
# found ZERO lugs and silo dispatch was dead. advisors is the sibling case in v4
# (WAI-Harness/spoke/advisors, not under local/).
_SPOKE_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from wai_paths import resolve_wai_root, advisors_dir
    _BASE, _MODE = resolve_wai_root(str(_SPOKE_ROOT))
    _BASE = _BASE or str(_SPOKE_ROOT / "WAI-Spoke")
    _ADVISORS = advisors_dir(str(_SPOKE_ROOT), _MODE) or str(Path(_BASE) / "advisors")
except Exception:
    _BASE = str(_SPOKE_ROOT / "WAI-Spoke")
    _ADVISORS = str(_SPOKE_ROOT / "WAI-Spoke" / "advisors")

FRAMEWORK_ROOT = Path(_BASE)  # retained for back-compat (working-state base)
BYTYPE_DIR = Path(_BASE) / "lugs" / "bytype"
SILOS_DIR = Path(_ADVISORS) / "autopilot" / "silos"
CONFIG_FILE = Path(_ADVISORS) / "autopilot" / "config.json"

SUBAGENT_MAX_LUGS = 2        # all-haiku silos at or below this → sub-agent mode
AUTOPILOT_MAX_LUGS = 15      # above this → gastown+autopilot
HOT_SPOT_HEAT = 50.0         # heat threshold triggering review gate check
HOT_SPOT_MEMBERS = 5         # member count threshold triggering review gate check
TOKENS_PER_LUG = {"haiku": 8_000, "sonnet": 20_000, "opus": 40_000}
LANE_TOKEN_BUDGET = 100_000  # conservative estimate per lane

DISPATCH_WEIGHTS_DEFAULT = {"haiku": 1, "sonnet": 3, "opus": 8}
DISPATCH_THRESHOLD_DEFAULT = 30


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config() -> Dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _compute_dispatch_score(lugs: List[Dict[str, Any]], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compute model-weighted dispatch score and return score metadata."""
    cfg = config or {}
    weights = cfg.get("dispatch_weights", DISPATCH_WEIGHTS_DEFAULT)
    threshold = cfg.get("dispatch_score_threshold", DISPATCH_THRESHOLD_DEFAULT)

    counts: Dict[str, int] = {}
    score = 0
    for lug in lugs:
        model = str(lug.get("model_fit", "sonnet")).lower()
        pt = weights.get(model, weights.get("sonnet", 3))
        score += pt
        counts[model] = counts.get(model, 0) + 1

    parts = [
        f"{n} {m} ({n * weights.get(m, 3)} pts)"
        for m, n in sorted(counts.items())
        if n > 0
    ]
    return {
        "dispatch_score": score,
        "dispatch_score_breakdown": " + ".join(parts) if parts else "0 lugs",
        "threshold": threshold,
        "flight_control_recommended": score > threshold,
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_open_lugs() -> List[Dict[str, Any]]:
    lugs: List[Dict[str, Any]] = []
    if not BYTYPE_DIR.exists():
        return lugs
    for type_dir in sorted(BYTYPE_DIR.iterdir()):
        if not type_dir.is_dir():
            continue
        open_dir = type_dir / "open"
        if not open_dir.exists():
            continue
        for lug_file in sorted(open_dir.glob("*.json")):
            try:
                d = json.loads(lug_file.read_text())
                d.setdefault("id", d.get("i", lug_file.stem))
                d.setdefault("type", d.get("ty", type_dir.name))
                d["_file"] = str(lug_file)
                lugs.append(d)
            except (json.JSONDecodeError, OSError):
                continue
    return lugs


def _normalize_path(raw: str) -> str:
    """Strip target_files annotations like ' — NEW', ' — EDIT', ' (optional)', etc."""
    for sep in (" — ", " - (", " (", "\t"):
        if sep in raw:
            raw = raw.split(sep)[0]
    return raw.strip()


def _get_target_files(lug: Dict[str, Any]) -> List[str]:
    raw = lug.get("target_files") or lug.get("files_to_edit") or []
    if isinstance(raw, str):
        raw = [raw]
    return [_normalize_path(f) for f in raw if f and f.strip()]


def _lug_score(lug: Dict[str, Any]) -> float:
    urgency = lug.get("urgency") or 5
    roi = lug.get("roi") or lug.get("impact") or 5
    try:
        return float(urgency) * float(roi)
    except (TypeError, ValueError):
        return 25.0


# ---------------------------------------------------------------------------
# Conflict graph — Union-Find
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self) -> None:
        self._parent: Dict[str, str] = {}
        self._rank: Dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self._parent:
            self._parent[x] = x
            self._rank[x] = 0
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1


def _build_conflict_graph(
    lugs: List[Dict[str, Any]],
) -> Tuple[_UnionFind, Dict[str, Set[str]], Dict[str, List[str]]]:
    uf = _UnionFind()
    file_to_ids: Dict[str, Set[str]] = defaultdict(set)
    id_to_files: Dict[str, List[str]] = {}

    for lug in lugs:
        lid = lug["id"]
        uf.find(lid)
        files = _get_target_files(lug)
        id_to_files[lid] = files
        for f in files:
            file_to_ids[f].add(lid)

    for f, ids in file_to_ids.items():
        ids_list = list(ids)
        for i in range(1, len(ids_list)):
            uf.union(ids_list[0], ids_list[i])

    return uf, file_to_ids, id_to_files


def _group_by_component(
    lugs: List[Dict[str, Any]], uf: _UnionFind
) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for lug in lugs:
        groups[uf.find(lug["id"])].append(lug)
    return dict(groups)


# ---------------------------------------------------------------------------
# Per-silo analysis
# ---------------------------------------------------------------------------

def _identify_pioneer(
    component: List[Dict[str, Any]],
    id_to_files: Dict[str, List[str]],
    file_to_ids: Dict[str, Set[str]],
) -> Tuple[Optional[str], int]:
    """Lug whose removal frees the most other component members."""
    if len(component) <= 1:
        return None, 0
    member_ids = {lug["id"] for lug in component}
    best_id: Optional[str] = None
    best_count = 0
    for lug in component:
        lid = lug["id"]
        freed: Set[str] = set()
        for f in id_to_files.get(lid, []):
            for other in file_to_ids.get(f, set()):
                if other != lid and other in member_ids:
                    freed.add(other)
        if len(freed) > best_count:
            best_count = len(freed)
            best_id = lid
    return best_id, best_count


def _check_review_gate(
    component: List[Dict[str, Any]],
    all_by_id: Dict[str, Dict[str, Any]],
    id_to_files: Dict[str, List[str]],
    open_spec_ids: Set[str],
) -> Optional[str]:
    """Return a description of the review concern if one exists, else None."""
    member_ids = {lug["id"] for lug in component}
    component_files: Set[str] = set()
    for lug in component:
        component_files.update(id_to_files.get(lug["id"], []))

    for lug in component:
        for blocker in lug.get("blocked_by") or lug.get("dependencies") or []:
            if not blocker or blocker in member_ids:
                continue
            if blocker in open_spec_ids:
                return f"blocked by open spec: {blocker}"
            if blocker in all_by_id:
                return f"blocked by open lug: {blocker}"

    for spec_id in open_spec_ids:
        if spec_id in member_ids:
            continue
        spec_files = set(id_to_files.get(spec_id, []))
        overlap = component_files & spec_files
        if overlap:
            sample = list(overlap)[:2]
            return f"open spec {spec_id} overlaps shared files: {', '.join(sample)}"

    return None


def _select_execution_mode(component: List[Dict[str, Any]]) -> str:
    count = len(component)
    model_fits = [str(lug.get("model_fit", "sonnet")).lower() for lug in component]
    has_gastown = any(lug.get("execution_mode") == "gastown" for lug in component)
    if has_gastown or count > AUTOPILOT_MAX_LUGS:
        return "gastown+autopilot"
    if all(m == "haiku" for m in model_fits) and count <= SUBAGENT_MAX_LUGS:
        return "sub-agent"
    return "autopilot"


def _estimate_tokens(component: List[Dict[str, Any]]) -> int:
    total = 0
    for lug in component:
        model = str(lug.get("model_fit", "sonnet")).lower()
        total += TOKENS_PER_LUG.get(model, TOKENS_PER_LUG["sonnet"])
    return total


# ---------------------------------------------------------------------------
# Float distribution
# ---------------------------------------------------------------------------

def _distribute_floats(
    float_lugs: List[Dict[str, Any]],
    components: List[List[Dict[str, Any]]],
) -> List[List[Dict[str, Any]]]:
    import heapq
    heap = [(len(c), i) for i, c in enumerate(components)]
    heapq.heapify(heap)
    for lug in float_lugs:
        count, idx = heapq.heappop(heap)
        components[idx].append(lug)
        heapq.heappush(heap, (count + 1, idx))
    return components


# ---------------------------------------------------------------------------
# Scout/capacity fill
# ---------------------------------------------------------------------------

def _find_scout_ids(all_lugs: List[Dict[str, Any]]) -> List[str]:
    scouts = []
    scout_types = {"spec", "hypothesis", "idea"}
    for lug in all_lugs:
        tags = lug.get("tags") or []
        lug_type = str(lug.get("type", "")).lower()
        title = str(lug.get("title", lug.get("t", ""))).lower()
        if (
            "scout" in tags or "expedition" in tags
            or lug_type in scout_types
            or any(kw in title for kw in ("scout", "expedition", "research", "survey"))
        ):
            scouts.append(lug["id"])
    return scouts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_flight_control(output_dir: Optional[Path] = None) -> Dict[str, Any]:
    output_dir = output_dir or SILOS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    config = _load_config()
    all_lugs = _load_open_lugs()
    if not all_lugs:
        return {"error": "no open lugs found", "total_lugs": 0, "silos": []}

    all_by_id = {lug["id"]: lug for lug in all_lugs}
    open_spec_ids = {
        lug["id"] for lug in all_lugs
        if str(lug.get("type", "")).lower() == "spec"
    }
    scout_ids = _find_scout_ids(all_lugs)

    lugs_with_files = [l for l in all_lugs if _get_target_files(l)]
    float_lugs = [l for l in all_lugs if not _get_target_files(l)]

    uf, file_to_ids, id_to_files = _build_conflict_graph(lugs_with_files)
    components_map = _group_by_component(lugs_with_files, uf)
    component_list: List[List[Dict[str, Any]]] = list(components_map.values())

    if not component_list:
        component_list = [[]]

    component_list = _distribute_floats(float_lugs, component_list)
    component_list = [c for c in component_list if c]

    scout_pool = list(scout_ids)
    silo_data = []

    for component in component_list:
        heat = sum(_lug_score(l) for l in component) + len(component)
        pioneer_id, pioneer_unlocks = _identify_pioneer(component, id_to_files, file_to_ids)

        is_hot = heat >= HOT_SPOT_HEAT or len(component) >= HOT_SPOT_MEMBERS
        review_gate = (
            _check_review_gate(component, all_by_id, id_to_files, open_spec_ids)
            if is_hot else None
        )

        exec_mode = _select_execution_mode(component)
        est_tokens = _estimate_tokens(component)
        remaining = max(0, LANE_TOKEN_BUDGET - est_tokens)

        capacity_fill: List[str] = []
        if remaining >= 15_000 and scout_pool:
            capacity_fill = scout_pool[:2]
            scout_pool = scout_pool[2:]

        silo_data.append({
            "heat": round(heat, 1),
            "lug_count": len(component),
            "lug_ids": [l["id"] for l in component],
            "pioneer": pioneer_id,
            "pioneer_unlocks": pioneer_unlocks,
            "execution_mode": exec_mode,
            "review_gate": review_gate,
            "estimated_tokens": est_tokens,
            "capacity_fill": capacity_fill,
        })

    silo_data.sort(key=lambda s: s["heat"], reverse=True)
    for i, silo in enumerate(silo_data):
        silo["silo_id"] = f"silo-{i}"
        silo["manifest"] = f"silo-{i}.json"

    advice = []
    for silo in silo_data:
        if silo["review_gate"]:
            advice.append(
                f"{silo['silo_id']}: REVIEW GATE — {silo['review_gate']} (resolve before dispatch)"
            )
        elif silo["pioneer"]:
            advice.append(
                f"{silo['silo_id']}: dispatch pioneer first ({silo['pioneer']}) "
                f"— unlocks {silo['pioneer_unlocks']} parallel lugs"
            )
        if silo["capacity_fill"]:
            k = silo["estimated_tokens"] // 1000
            advice.append(
                f"{silo['silo_id']}: after completion fill remaining capacity with "
                + ", ".join(silo["capacity_fill"])
            )

    generated_at = datetime.now(timezone.utc).isoformat()
    score_meta = _compute_dispatch_score(all_lugs, config)
    attack_plan = {
        "generated_at": generated_at,
        "total_lugs": len(all_lugs),
        "lugs_with_files": len(lugs_with_files),
        "float_lugs": len(float_lugs),
        "recommended_lanes": len(silo_data),
        **score_meta,
        "silos": silo_data,
        "scheduling_advice": advice,
    }

    for silo in silo_data:
        manifest = {
            "silo_id": silo["silo_id"],
            "generated_at": generated_at,
            "lug_count": silo["lug_count"],
            "lug_ids": silo["lug_ids"],
            "pioneer": silo["pioneer"],
            "execution_mode": silo["execution_mode"],
        }
        (output_dir / silo["manifest"]).write_text(
            json.dumps(manifest, indent=2) + "\n"
        )

    (output_dir / "attack-plan.json").write_text(
        json.dumps(attack_plan, indent=2) + "\n"
    )

    return attack_plan


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _print_heat_map(plan: Dict[str, Any]) -> None:
    ts = plan["generated_at"][:19] + "Z"
    print(f"\n{'='*62}")
    print(f"  FLIGHT CONTROL — CONFLICT GRAPH HEAT MAP")
    print(f"  {ts}")
    print(f"{'='*62}")
    print(f"  Total open lugs : {plan['total_lugs']}")
    print(f"  With target_files: {plan['lugs_with_files']}   Float: {plan['float_lugs']}")
    print(f"  Silos           : {len(plan['silos'])}   Recommended lanes: {plan['recommended_lanes']}")
    print(f"{'='*62}\n")

    for silo in plan["silos"]:
        bar_len = min(20, max(1, int(silo["heat"] / 10)))
        bar = "█" * bar_len
        gate = "  ⚠  REVIEW GATE" if silo["review_gate"] else ""
        print(
            f"  {silo['silo_id']:8s}  [{bar:<20s}]  "
            f"heat={silo['heat']:6.0f}  {silo['lug_count']:2d} lugs  "
            f"{silo['execution_mode']:<22s}{gate}"
        )
        if silo["pioneer"]:
            print(f"           pioneer: {silo['pioneer']} → unlocks {silo['pioneer_unlocks']}")
        if silo["review_gate"]:
            print(f"           gate   : {silo['review_gate']}")
        print()

    if plan["scheduling_advice"]:
        print(f"  SCHEDULING ADVICE")
        print(f"  {'─'*52}")
        for line in plan["scheduling_advice"]:
            print(f"  • {line}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Flight Control: conflict graph + attack plan for concurrent autopilot"
    )
    parser.add_argument("--output-dir", help="Directory for manifests (default: WAI-Spoke/advisors/autopilot/silos/)")
    parser.add_argument("--quiet", action="store_true", help="Suppress heat map display")
    parser.add_argument("--json", action="store_true", help="Print attack plan JSON to stdout")
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else None
    plan = run_flight_control(output_dir=out_dir)

    if "error" in plan:
        print(f"Error: {plan['error']}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(plan, indent=2))
    elif not args.quiet:
        _print_heat_map(plan)
        resolved_dir = out_dir or SILOS_DIR
        print(f"  Attack plan → {resolved_dir / 'attack-plan.json'}")
        print()
