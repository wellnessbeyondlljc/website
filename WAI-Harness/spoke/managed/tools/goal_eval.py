#!/usr/bin/env python3
"""goal_eval — score the goal-driven-autopilot system against its STATED GOALS.

Two layers:
  CAPABILITY scorecard (G1..G6) — exercises the real functions in ISOLATED tmp stores
    so the checks are deterministic and don't pollute the live store. Proves the wheel
    can: record blocks, remember them, drive (replan), never crash, run clean cycles,
    and measure its own goals.
  PRODUCTION kpi — the live measured-goal snapshot (goal_measure) reflecting real AP
    activity in mywheel's actual store.

Run: python3 goal_eval.py --root <repo-root> --initiative <id>
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capgraph_blocks as cb  # noqa: E402
import goal_planner as gp  # noqa: E402
import ap_cycle as ac  # noqa: E402
import goal_measure as gm  # noqa: E402


def _tmp_local():
    d = tempfile.mkdtemp()
    (Path(d) / "WAI-Harness" / "spoke" / "local" / "capabilitygraph").mkdir(parents=True)
    return d


def _check(name: str, ok: bool, detail: str = "") -> Dict[str, Any]:
    return {"goal": name, "pass": bool(ok), "detail": detail}


def capability_scorecard() -> List[Dict[str, Any]]:
    out = []

    # G1 — failures become learning (record + dedup)
    t = _tmp_local()
    lug = {"id": "g1", "type": "impl"}
    cb.record_block(lug, "stall", "x", spoke_local=t)
    cb.record_block(lug, "stall", "x", spoke_local=t)
    s = cb.summarize(t)
    out.append(_check("G1 failures-become-learning", s["total_occurrences"] == 2 and s["total_antipatterns"] == 1,
                      f"occurrences={s['total_occurrences']} entries={s['total_antipatterns']} (dedup)"))

    # G2 — remembered, not re-hit (consult)
    t = _tmp_local()
    cb.record_block({"id": "seen", "type": "impl"}, "stall", spoke_local=t)
    hit = cb.consult({"id": "seen"}, spoke_local=t)
    miss = cb.consult({"id": "fresh"}, spoke_local=t)
    out.append(_check("G2 remembered-not-rehit", len(hit) == 1 and miss == [],
                      f"consult hit={len(hit)} miss={len(miss)}"))

    # G3 — drives on block (ladder routes correctly across rungs)
    t = _tmp_local()
    r1 = gp.replan_on_block({"id": "a"}, "precondition_unmet", "file_exists: x", ctx=gp.new_ctx(), spoke_local=t)
    r2 = gp.replan_on_block({"id": "b", "goal_id": "g"}, "stall", ctx=gp.new_ctx(), spoke_local=t,
                            sibling_lookup=lambda l: "sib")
    r4 = gp.replan_on_block({"id": "c"}, "stall", ctx=gp.new_ctx(), spoke_local=t)
    drives = r1["action"] == "requeue_setup" and r2["action"] == "substitute" and r4["action"] == "escalate"
    out.append(_check("G3 drives-on-block", drives,
                      f"synthesize={r1['action']} substitute={r2['action']} escalate={r4['action']}"))

    # G4 — never breaks AP (robustness)
    t = _tmp_local()
    import unittest.mock as mock
    with mock.patch.object(cb, "_atomic_write", side_effect=OSError("boom")):
        safe = cb.record_block({"id": "x"}, "stall", spoke_local=t) is None
    rp_safe = gp.replan_on_block({"id": "y", "goal_id": "g"}, "stall", ctx=gp.new_ctx(), spoke_local=t,
                                 sibling_lookup=lambda l: (_ for _ in ()).throw(RuntimeError("boom")))["action"] == "escalate"
    out.append(_check("G4 never-breaks-AP", safe and rp_safe, f"record_safe={safe} replan_safe={rp_safe}"))

    # G5 — clean platform per cycle (ap_cycle transaction)
    blocked = not ac.plan_start("s", {}, main_clean=False, main_ff=True, verify_ok=False)["reconcile_ok"]
    clean = ac.plan_start("s", {"cycle": 1}, main_clean=True, main_ff=True, verify_ok=True)["reconcile_ok"]
    merge = ac.plan_finish("ap/s/c1", True, 3)["action"] == "merge"
    quar = ac.plan_finish("ap/s/c1", False, 3)["action"] == "quarantine"
    out.append(_check("G5 clean-platform-per-cycle", blocked and clean and merge and quar,
                      f"dirty-blocked={blocked} clean-ok={clean} pass-merge={merge} fail-quarantine={quar}"))

    return out


def run(root: str, initiative_id: str) -> Dict[str, Any]:
    caps = capability_scorecard()
    # G6 — goals measured (production, real store)
    kpi = gm.measure_initiative(root, initiative_id)
    g6 = kpi["measured"] >= 5
    caps.append(_check("G6 goals-measured", g6,
                       f"measured={kpi['measured']}/{kpi['total']} met={kpi['met']}"))
    passed = sum(1 for c in caps if c["pass"])
    # DRIVE RATE — the core goal: of real blocks the ladder processed, how many were
    # re-routed (substituted/synthesized) vs escalated. This is "AP drives on block".
    local = cb._find_spoke_local(str(Path(root) / "WAI-Harness" / "spoke" / "local"))
    drove = total_res = 0
    if local:
        g = cb._load_graph(local / cb.LOCAL_GRAPH)
        for e in g.get("entries", []):
            if e.get("kind") != "antipattern" or not e.get("resolution"):
                continue
            total_res += 1
            if e.get("resolution") in ("substituted", "synthesized"):
                drove += 1
    drive_rate = round(100.0 * drove / total_res, 1) if total_res else 0.0
    return {"capability_score": f"{passed}/{len(caps)}", "capabilities": caps,
            "production_kpi": kpi, "drive_rate_pct": drive_rate,
            "drive_detail": f"{drove}/{total_res} real blocks re-routed (rest escalated)"}


def render(rep: Dict[str, Any]) -> str:
    lines = ["", "════ EFFECTIVENESS SCORECARD vs stated goals ════"]
    for c in rep["capabilities"]:
        mark = "✓ PASS" if c["pass"] else "✗ FAIL"
        lines.append(f"  {mark}  {c['goal']:<32} {c['detail']}")
    lines.append(f"  ── CAPABILITY SCORE: {rep['capability_score']}")
    k = rep["production_kpi"]
    lines.append(f"  ── PRODUCTION KPI: {k['measured']}/{k['total']} goals measured, {k['met']} met (live store)")
    lines.append(f"  ── DRIVE RATE: {rep['drive_rate_pct']}%  ({rep['drive_detail']})")
    lines.append("═════════════════════════════════════════════════")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="goal_eval — effectiveness scorecard")
    ap.add_argument("--root", required=True)
    ap.add_argument("--initiative", default="initiative-goal-driven-autopilot-v1")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rep = run(args.root, args.initiative)
    print(json.dumps(rep, indent=2) if args.json else render(rep))
