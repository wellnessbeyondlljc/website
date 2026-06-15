#!/usr/bin/env python3
"""historian_gate_mine.py — the ANALYZE→EVOLVE terminal of the self-rolling loop.

(impl-historian-gate-mining-v1) Gate events accumulate in gate-log; this pass
turns them into insight WITHOUT the two failure modes:

  1. over-cycling — running every session on thin data is noise + wasted cost.
     So mining is gated by a DATA-SUFFICIENCY trigger Historian declares for
     itself: run only when (new events since last mine >= EVENTS_FLOOR) OR
     (sessions since last mine >= SESSIONS_FLOOR), whichever first, and NEVER
     when new events < MIN_FLOOR. The trigger evaluation is recorded so "why
     did/didn't it run" is observable.

  2. isolated mutation — a spoke that detects a pattern and self-evolves its own
     harness in place makes the fleet diverge and never benefit. So discoveries
     do NOT self-adopt locally; fleet-worthy ones BUBBLE UP to the hub as
     complete change-lugs for collective assessment (curator model). Only
     clearly spoke-specific quirks stay local, labelled as such.

API:
  evaluate_trigger(new_events, sessions_since, floors=None) -> {"run": bool, "reason": str}
  mine(events) -> {"recurring_halts": [...], "regressions": [...], "calibration": [...]}
  write_candidates(candidates, patterns_dir) -> [paths]
  bubble_up(candidate, hub_incoming, attribution) -> path
  pattern_health(events, open_candidates, trigger_fired) -> dict
  close_loop(pre_baseline_rate, post_events, flow_id) -> dict
"""
import argparse
import json
import os
import sys

def _attr(contributor="historian", kind="agent"):
    """Return a {actor, kind} attribution dict (normalizes lug_utils' tuple)."""
    try:
        import lug_utils
        actor, k = lug_utils.resolve_attribution(".", contributor)
        return {"actor": actor, "kind": k}
    except Exception:  # fallback if lug_utils unavailable
        return {"actor": f"session-unknown.{contributor}", "kind": kind}

DEFAULT_FLOORS = {"EVENTS_FLOOR": 50, "SESSIONS_FLOOR": 5, "MIN_FLOOR": 10}
RECURRENCE_SESSIONS = 3        # same halt across >=3 sessions -> candidate
REGRESSION_DELTA = 0.15        # >15% version-bounded approval drop -> alert
OVER_STRICT_HALT_RATE = 0.80   # >80% halt rate at a step -> over-strict calibration


def evaluate_trigger(new_events, sessions_since, floors=None):
    """Data-sufficiency gate. Returns whether to run + an observable reason."""
    f = {**DEFAULT_FLOORS, **(floors or {})}
    if new_events < f["MIN_FLOOR"]:
        return {"run": False, "reason": f"new_events {new_events} < MIN_FLOOR {f['MIN_FLOOR']} "
                f"(skip — no over-cycling on thin data)", "new_events": new_events}
    if new_events >= f["EVENTS_FLOOR"]:
        return {"run": True, "reason": f"new_events {new_events} >= EVENTS_FLOOR {f['EVENTS_FLOOR']}",
                "new_events": new_events}
    if sessions_since >= f["SESSIONS_FLOOR"]:
        return {"run": True, "reason": f"sessions_since {sessions_since} >= SESSIONS_FLOOR "
                f"{f['SESSIONS_FLOOR']}", "new_events": new_events}
    return {"run": False, "reason": f"new_events {new_events} below EVENTS_FLOOR and "
            f"sessions_since {sessions_since} below SESSIONS_FLOOR (wait for more signal)",
            "new_events": new_events}


def mine(events):
    """Convert gate events into proposals: recurring halts, approval regressions,
    and calibration signals. Returns proposal lists (NOT adopted changes)."""
    # recurring halt: same (flow_id, step_id) halted across >= N distinct sessions
    halt_sessions = {}
    step_totals, step_halts = {}, {}
    for e in events:
        key = (e.get("flow_id"), e.get("step_id"))
        step_totals[key] = step_totals.get(key, 0) + 1
        if e.get("disposition") == "halted":
            halt_sessions.setdefault(key, set()).add(e.get("session_id"))
            step_halts[key] = step_halts.get(key, 0) + 1
    recurring = [{"type": "recurring_halt", "flow_id": k[0], "step_id": k[1],
                  "session_count": len(s), "evidence": f"halted in {len(s)} distinct sessions"}
                 for k, s in halt_sessions.items() if len(s) >= RECURRENCE_SESSIONS]

    # approval regression: version-bounded approval drop between consecutive versions
    by_flow_ver = {}
    for e in events:
        if e.get("disposition") in ("approved", "escalate"):
            fv = (e.get("flow_id"), e.get("flow_version", 1))
            d = by_flow_ver.setdefault(fv, {"approved": 0, "terminal": 0})
            d["terminal"] += 1
            if e.get("disposition") == "approved":
                d["approved"] += 1
    rates = {fv: (d["approved"] / d["terminal"]) for fv, d in by_flow_ver.items() if d["terminal"]}
    regressions = []
    flows = {fv[0] for fv in rates}
    for flow in flows:
        versions = sorted(v for (f, v) in rates if f == flow)
        for i in range(1, len(versions)):
            prev, cur = rates[(flow, versions[i - 1])], rates[(flow, versions[i])]
            if prev - cur > REGRESSION_DELTA:
                regressions.append({"type": "regression", "flow_id": flow,
                                    "from_version": versions[i - 1], "to_version": versions[i],
                                    "approval_drop": round(prev - cur, 3),
                                    "evidence": f"approval {prev:.0%} -> {cur:.0%}"})

    # calibration: over-strict (halt rate > 80%); too-loose (approved then downstream failure)
    calibration = []
    for key, total in step_totals.items():
        hr = step_halts.get(key, 0) / total if total else 0
        if hr > OVER_STRICT_HALT_RATE:
            calibration.append({"type": "calibration", "signal": "over-strict",
                                "flow_id": key[0], "step_id": key[1], "halt_rate": round(hr, 3)})
    for e in events:
        ev = e.get("evidence") or {}
        if e.get("disposition") == "approved" and isinstance(ev, dict) and ev.get("downstream_failed"):
            calibration.append({"type": "calibration", "signal": "too-loose",
                                "flow_id": e.get("flow_id"), "step_id": e.get("step_id"),
                                "evidence": "approved but downstream failed"})
    return {"recurring_halts": recurring, "regressions": regressions, "calibration": calibration}


def write_candidates(candidates, patterns_dir):
    """Persist each finding as a PROPOSAL object in the historian patterns folder.
    These are proposals, not adopted changes."""
    os.makedirs(patterns_dir, exist_ok=True)
    paths = []
    for i, c in enumerate(candidates):
        c = {**c, "status": "candidate", "adopted": False}
        slug = f"{c.get('type','finding')}-{c.get('flow_id','x')}-{c.get('step_id', i)}".replace("/", "_")
        p = os.path.join(patterns_dir, f"candidate-{slug}.json")
        json.dump(c, open(p, "w"), indent=2)
        paths.append(p)
    return paths


def bubble_up(candidate, hub_incoming, attribution=None, fleet_worthy=True):
    """Deliver a fleet-worthy discovery UP to the hub as a complete change-lug
    for collective assessment. The spoke does NOT self-adopt. Local-only quirks
    (fleet_worthy=False) are not delivered — they stay local, labelled."""
    if not fleet_worthy:
        return None
    os.makedirs(hub_incoming, exist_ok=True)
    attribution = attribution or _attr("historian", "agent")
    slug = f"{candidate.get('type','finding')}-{candidate.get('flow_id','x')}".replace("/", "_")
    lug = {
        "id": f"change-historian-{slug}-v1", "type": "change", "status": "open",
        "routed_to": "hub", "source_spoke": "wheelwright-framework",
        "title": f"Gate-mined proposal: {candidate.get('type')} in {candidate.get('flow_id')}",
        "what_changed": "proposal only — not self-adopted",
        "why": "gate-mining detected a fleet-relevant pattern; bubbling up for curator assessment",
        "candidate": candidate, "resolve_attribution": attribution, "kind": attribution.get("kind", "agent"),
        "self_adopted_locally": False,
        "delivered_at": "2026-06-09T00:00:00Z",
    }
    p = os.path.join(hub_incoming, f"{lug['id']}.json")
    json.dump(lug, open(p, "w"), indent=2)
    return p


def pattern_health(events, open_candidates, trigger_fired):
    """The wakeup 'Pattern Health' section: first-attempt approval per flow, halt
    frequency per step, open candidate count, and whether the trigger fired."""
    first_attempt, terminal, halts = {}, {}, {}
    for e in events:
        flow = e.get("flow_id")
        if e.get("disposition") in ("approved", "escalate"):
            terminal[flow] = terminal.get(flow, 0) + 1
            if e.get("disposition") == "approved" and int(e.get("attempt", 1)) == 1:
                first_attempt[flow] = first_attempt.get(flow, 0) + 1
        if e.get("disposition") == "halted":
            k = f"{flow}/{e.get('step_id')}"
            halts[k] = halts.get(k, 0) + 1
    fa_rate = {f: round(first_attempt.get(f, 0) / terminal[f], 3) for f in terminal}
    return {"first_attempt_approval_rate": fa_rate, "halt_frequency_per_step": halts,
            "open_candidates": len(open_candidates), "trigger_fired": bool(trigger_fired)}


def close_loop(pre_baseline_rate, post_events, flow_id):
    """AC9: after a canonicalized teaching is adopted, measure post-adoption halt
    rate against the pre-adoption baseline so the evolution is quantified."""
    rel = [e for e in post_events if e.get("flow_id") == flow_id]
    halts = sum(1 for e in rel if e.get("disposition") == "halted")
    post_rate = round(halts / len(rel), 3) if rel else None
    return {"flow_id": flow_id, "pre_baseline_halt_rate": pre_baseline_rate,
            "post_adoption_halt_rate": post_rate,
            "improved": (post_rate is not None and pre_baseline_rate is not None
                         and post_rate < pre_baseline_rate)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="historian gate-mining pass")
    ap.add_argument("--gate-log", default="WAI-Spoke/patterns/gate-log.jsonl")
    ap.add_argument("--new-events", type=int, required=True)
    ap.add_argument("--sessions-since", type=int, default=0)
    ap.add_argument("--patterns-dir", default="WAI-Spoke/advisors/historian/patterns")
    a = ap.parse_args(argv)
    trig = evaluate_trigger(a.new_events, a.sessions_since)
    if not trig["run"]:
        print(json.dumps({"ran": False, "reason": trig["reason"]}))
        return 0
    events = [json.loads(l) for l in open(a.gate_log)] if os.path.exists(a.gate_log) else []
    found = mine(events)
    cands = found["recurring_halts"] + found["regressions"] + found["calibration"]
    paths = write_candidates(cands, a.patterns_dir)
    print(json.dumps({"ran": True, "candidates": len(paths),
                      "health": pattern_health(events, cands, True)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
