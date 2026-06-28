#!/usr/bin/env python3
"""goal_measure — P3: make initiative goals MEASURED, computed from live telemetry.

Reuses the advisor pilot_contract.kpis shape for success_criteria, wires the dormant
`measuring` lifecycle_state + the empty spoke/local/kpi/ dir. A goal becomes an object:
  {id, statement, success_criteria:{name,definition,baseline_method,target},
   metric, baseline, current, tracked_via, status: open|measuring|met}

METRICS is a registry of metric_name -> fn(ctx)->number, computed from real telemetry
(the capgraph block-store, the initiative index, the test suite, ap_cycle). Goals carrying
a registered `metric` get their `current` refreshed and `status` flipped toward `met`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capgraph_blocks as cb  # noqa: E402
import ap_cycle as ac  # noqa: E402

INDEX_REL = "WAI-Harness/spoke/local/initiatives/index.json"
KPI_REL = "WAI-Harness/spoke/local/kpi"
MANAGED = Path(__file__).resolve().parent

METRICS: Dict[str, Callable[[Dict[str, Any]], float]] = {}

# ---------------------------------------------------------------------------
# Normalize goals (backward-compat: bare str -> dict)
# ---------------------------------------------------------------------------

def normalize_goal(g: Any) -> Dict[str, Any]:
    """Normalize an initiative goal to the measured-goal-v1 dict shape.

    Accepts a bare string (legacy) or a dict (already normalized).
    A bare string maps to {statement, status: open}; dicts pass through unchanged.
    Route ALL initiative.goals[] reads through this so a mixed index never crashes.
    """
    if isinstance(g, str):
        return {"statement": g, "status": "open"}
    return g


def metric(name: str):
    def deco(fn):
        METRICS[name] = fn
        return fn
    return deco


@metric("blocks_recorded_total")
def _blocks_recorded_total(ctx):
    return cb.summarize(ctx["spoke_local"]).get("total_occurrences", 0)


@metric("antipattern_resolution_pct")
def _antipattern_resolution_pct(ctx):
    local = cb._find_spoke_local(ctx["spoke_local"])
    if not local:
        return 0.0
    g = cb._load_graph(local / cb.LOCAL_GRAPH)
    aps = [e for e in g.get("entries", []) if e.get("kind") == "antipattern"]
    if not aps:
        return 0.0
    resolved = sum(1 for e in aps if e.get("resolution"))
    return round(100.0 * resolved / len(aps), 1)


@metric("goals_measured_pct")
def _goals_measured_pct(ctx):
    it = _find_initiative(ctx["root"], ctx["initiative_id"])
    goals = (it or {}).get("goals", [])
    if not goals:
        return 0.0
    measured = sum(1 for g in [normalize_goal(g) for g in goals] if g.get("success_criteria"))
    return round(100.0 * measured / len(goals), 1)


@metric("expediter_blocks_recorded")
def _expediter_blocks_recorded(ctx):
    local = cb._find_spoke_local(ctx["spoke_local"])
    if not local:
        return 0
    g = cb._load_graph(local / cb.LOCAL_GRAPH)
    return sum(int(e.get("occurrences", 0)) for e in g.get("entries", [])
               if e.get("kind") == "antipattern" and e.get("block_class") == "blocked_by")


@metric("portfolio_top_initiative_chosen")
def _portfolio_top_initiative_chosen(ctx):
    try:
        import portfolio as pf
        r = pf.rank_spoke(ctx["root"], budget=8)
        return 1.0 if r.get("chosen_initiative") else 0.0
    except Exception:
        return 0.0


@metric("verify_then_define_gate")
def _verify_then_define_gate(ctx):
    # HONEST: 1.0 only when the gate is actually BUILT + its tests pass. (Full conductor/
    # interview wiring is downstream; this measures the verifiable gate core.)
    tool = MANAGED / "verify_then_define.py"  # MANAGED is the tools/ dir
    if not tool.exists():
        return 0.0
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/test_verify_then_define.py", "-q"],
                       cwd=str(MANAGED.parent), capture_output=True, text=True)
    return 1.0 if r.returncode == 0 else 0.0


@metric("subsystem_tests_pass")
def _subsystem_tests_pass(ctx):
    tests = ["tests/test_capgraph_blocks.py", "tests/test_goal_planner.py", "tests/test_ap_cycle.py"]
    r = subprocess.run([sys.executable, "-m", "pytest", *tests, "-q"],
                       cwd=str(MANAGED.parent), capture_output=True, text=True)
    return 1.0 if r.returncode == 0 else 0.0


@metric("ap_cycle_safety_gate")
def _ap_cycle_safety_gate(ctx):
    # the gate must REFUSE a cycle on a dirty/unverified platform
    blocked = ac.plan_start("mywheel", {"cycle": 0}, main_clean=False, main_ff=True, verify_ok=False)
    clean = ac.plan_start("mywheel", {"cycle": 0}, main_clean=True, main_ff=True, verify_ok=True)
    return 1.0 if (not blocked["reconcile_ok"] and clean["reconcile_ok"]) else 0.0


@metric("test_collection_errors")
def _test_collection_errors(ctx):
    """Count pytest collection errors (ERROR lines in --collect-only output)."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q", "--tb=no"],
        cwd=str(MANAGED.parent), capture_output=True, text=True,
    )
    return sum(1 for line in (r.stdout + r.stderr).splitlines() if "ERROR" in line)


# ---------- PathGraph emit (report-only; never mutates PathGraph own semantics) ----------

def _emit_pathgraph_fulfilled(root: str, initiative_id: str, goal: Dict[str, Any]) -> None:
    """Append a goal_fulfilled event to spoke/local/pathgraph/history.jsonl."""
    pg_dir = Path(root) / "WAI-Harness" / "spoke" / "local" / "pathgraph"
    pg_dir.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "op_type": "goal_fulfilled",
        "initiative_id": initiative_id,
        "goal_id": goal.get("id", ""),
        "statement": goal.get("statement", ""),
        "metric": goal.get("metric"),
        "current": goal.get("current"),
    }
    with open(pg_dir / "history.jsonl", "a") as fh:
        fh.write(json.dumps(entry) + "\n")


# ---------- index helpers ----------

def _index_path(root):
    return Path(root) / INDEX_REL


def _load_index(root):
    return json.loads(_index_path(root).read_text())


def _find_initiative(root, initiative_id):
    for it in _load_index(root).get("initiatives", []):
        if it.get("id") == initiative_id:
            return it
    return None


def _root_from(spoke_local):
    local = cb._find_spoke_local(spoke_local)
    if local is None:
        return None
    # spoke/local -> repo root is two parents above WAI-Harness
    for anc in local.parents:
        if (anc / INDEX_REL).exists():
            return anc
    return local.parents[2] if len(local.parents) > 2 else None


def measure_initiative(root, initiative_id) -> Dict[str, Any]:
    """Compute current for every measured goal, write kpi file, update the index."""
    idx = _load_index(root)
    spoke_local = str(Path(root) / "WAI-Harness" / "spoke" / "local")
    ctx = {"root": root, "spoke_local": spoke_local, "initiative_id": initiative_id}
    scored = {"initiative": initiative_id, "goals": [], "measured": 0, "met": 0, "total": 0}
    for it in idx.get("initiatives", []):
        if it.get("id") != initiative_id:
            continue
        raw_goals = it.get("goals", [])
        # Normalize all goals in-place: bare strings become {statement, status:open}
        goals = [normalize_goal(g) for g in raw_goals]
        it["goals"] = goals
        scored["total"] = len(goals)
        for g in goals:
            if not g.get("metric"):
                continue
            mname = g["metric"]
            fn = METRICS.get(mname)
            if not fn:
                continue
            try:
                cur = fn(ctx)
            except Exception as e:
                cur = None
                print(f"[goal_measure] metric {mname} failed: {e}", file=sys.stderr)
            prev_status = g.get("status")
            g["current"] = cur
            tgt = (g.get("success_criteria") or {}).get("target")
            met = _meets(cur, tgt)
            g["status"] = "met" if met else "measuring"
            scored["measured"] += 1
            scored["met"] += 1 if met else 0
            scored["goals"].append({"id": g.get("id"), "metric": mname, "current": cur,
                                    "target": tgt, "status": g["status"]})
            # emit PathGraph fulfilled when a goal first flips to met (report-only)
            if g["status"] == "met" and prev_status != "met":
                _emit_pathgraph_fulfilled(root, initiative_id, g)
        # flip lifecycle_state active->measuring when any goal has populated success_criteria
        if any(g.get("success_criteria") for g in goals):
            if it.get("lifecycle_state") in ("active", "approved", None):
                it["lifecycle_state"] = "measuring"
    # write kpi snapshot
    kpi_dir = Path(root) / KPI_REL
    kpi_dir.mkdir(parents=True, exist_ok=True)
    (kpi_dir / f"{initiative_id}.json").write_text(json.dumps(scored, indent=2))
    _index_path(root).write_text(json.dumps(idx, indent=2, ensure_ascii=False))
    return scored


def _meets(cur, target):
    if cur is None or target is None:
        return False
    try:
        # target like ">=1", "==0", "100", ">=100"
        t = str(target).strip()
        for op in (">=", "<=", "==", ">", "<"):
            if t.startswith(op):
                v = float(t[len(op):])
                return {">=": cur >= v, "<=": cur <= v, "==": cur == v,
                        ">": cur > v, "<": cur < v}[op]
        return float(cur) >= float(t)
    except (ValueError, TypeError):
        return False


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="goal_measure — compute measured-goal currents")
    ap.add_argument("--root", required=True)
    ap.add_argument("--initiative", required=True)
    args = ap.parse_args()
    print(json.dumps(measure_initiative(args.root, args.initiative), indent=2))
