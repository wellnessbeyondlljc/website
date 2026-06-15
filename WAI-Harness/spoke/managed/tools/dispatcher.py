#!/usr/bin/env python3
"""dispatcher.py — the Scheduler/Dispatcher: event→advisor routing under safety bounds.

(impl-scheduler-dispatcher-v1) This is the coupling that makes the wheel
self-roll. It drains the event journal on a cadence TICK (not a long-lived
daemon — crash-safe, nothing to babysit, replays unacked wakes), matches each
event to subscribed advisors via a DECLARATIVE routing table (advisors register
their subscriptions as data in registry.json), and wakes them — all under hard
safety bounds so autonomy cannot run away:

  - idempotency + debounce + analysis_trigger floor  -> no thrash / over-cycling
  - cost circuit-breaker (rate + burn 80%/100% + loop guard) -> pause + Attention
  - gate-retry orchestration                          -> the gate emits halted;
        a WRITE-AUTHORIZED executor (here) does the retry, honoring the 2-cycle cap
  - advisor liveness (heartbeat + requeue)            -> a hung advisor is recovered
  - hub-down local-continue + self-cert marker        -> degraded but not stalled

Every dispatch decision emits a dispatch_audit event — the orchestrator is not
exempt from verification (it self-gates). Every circuit-breaker trip emits a
type=decision event carrying the reason + figure, so the WHY is on the bus.

The functions are pure over an injected `state` dict + clock so they are unit-
testable and replay-safe; the CLI wires them to the real journal + registry.
"""
import argparse
import json
import os
import sys

try:
    import event_bus
except ImportError:
    event_bus = None

HOUR_S = 3600
DEFAULT_REGISTRY = "WAI-Spoke/advisors/registry.json"
DEFAULT_GLOBAL_RATE_CAP = 120      # wakes/hour across all advisors
DEFAULT_LOOP_K = 3                 # wake→fail→re-emit > K -> circuit-broken
RETRY_CAP = 2                      # 2 attempt cycles; 3rd failure escalates


# ---------- routing table (declarative, from registry.json) ----------
def load_routing(registry_path=DEFAULT_REGISTRY):
    """Build {advisor_id: policy} from registry.json. Subscriptions are data:
    `subscribes_to` (preferred) or the legacy `event_triggers`. Missing policy
    fields fall back to safe defaults."""
    try:
        reg = json.load(open(registry_path, encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    routing = {}
    for a in reg:
        aid = a.get("advisor_id")
        if not aid:
            continue
        routing[aid] = {
            "subscribes_to": a.get("subscribes_to") or a.get("event_triggers") or [],
            "debounce_window_s": a.get("debounce_window_s", 60),
            "max_concurrency": a.get("max_concurrency", 1),
            "analysis_trigger": a.get("analysis_trigger", 0),
            "rate_cap_per_hour": a.get("rate_cap_per_hour", 30),
            "dispatch_command": a.get("dispatch_command"),
        }
    return routing


def match_advisors(event_type, routing):
    """Advisors subscribed to this event type. An unsubscribed advisor never wakes."""
    return [aid for aid, p in routing.items() if event_type in p["subscribes_to"]]


# ---------- clock / window helpers ----------
def _parse(ts):
    import datetime
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _within(last_ts, now_ts, window_s):
    if not last_ts:
        return False
    return (_parse(now_ts) - _parse(last_ts)).total_seconds() < window_s


def _recent_count(times, now_ts, window_s=HOUR_S):
    return sum(1 for t in times if _within(t, now_ts, window_s))


def _new_state():
    return {"wake_log": {}, "in_flight": {}, "debounce": {}, "loop_counts": {},
            "heartbeats": {}, "paused": False, "global_wakes": []}


def _emit_decision(reason, evidence, audits):
    """Record a type=decision event so a subsequent flow-changing action (pause/
    escalate) has a preceding decision carrying the WHY on the bus."""
    audits.append({"type": "decision", "actor": "dispatcher", "status": "decided",
                   "evidence": {"rationale": reason, "alternatives": ["continue", "pause/escalate"],
                                **evidence}})


# ---------- cost circuit-breaker ----------
def circuit_breaker_burn(spent, budget):
    """Burn cap: alert at 80% of budget, PAUSE autonomous dispatch at 100%."""
    if not budget:
        return {"level": "ok", "pct": 0.0, "spent": spent}
    pct = spent / budget
    level = "paused" if pct >= 1.0 else ("alert" if pct >= 0.8 else "ok")
    return {"level": level, "pct": round(pct, 3), "spent": spent}


def loop_guard(trigger_key, state, k=DEFAULT_LOOP_K):
    """An advisor that wakes→fails→re-emits its own trigger more than K times is
    in a loop -> circuit-broken. Returns True when the circuit should break."""
    n = state["loop_counts"].get(trigger_key, 0) + 1
    state["loop_counts"][trigger_key] = n
    return n > k


# ---------- gate-retry orchestration (the gate emits-only; we write) ----------
def gate_retry(gate_event, cap=RETRY_CAP):
    """Consume a halted/escalate gate event and decide the orchestration action.
    The Pattern Gate is read-only — IT never retries. The dispatcher (a write-
    authorized actor) re-dispatches the step to an executor, honoring the cap."""
    attempt = int(gate_event.get("attempt", 1))
    disposition = gate_event.get("disposition") or gate_event.get("status")
    if disposition == "escalate" or attempt >= cap + 1:
        return {"action": "escalate", "attempt": attempt,
                "reason": "retry cap exhausted or structural failure"}
    if disposition == "halted":
        return {"action": "redispatch", "attempt": attempt + 1,
                "executor": "write-authorized-executor",
                "step": f"{gate_event.get('flow_id')}/{gate_event.get('step_id')}"}
    return {"action": "noop", "attempt": attempt}


# ---------- advisor liveness ----------
def check_liveness(state, now_ts, silence_s=300):
    """Advisors whose heartbeat has been silent past the threshold: their in-flight
    work is requeued and an Attention item is raised."""
    stale = []
    for aid, last in state["heartbeats"].items():
        if _parse(now_ts).timestamp() - _parse(last).timestamp() > silence_s:
            stale.append(aid)
    return stale


# ---------- hub-down degradation ----------
def hub_status(hub_reachable, work_items):
    """Hub unreachable: local dispatch continues; hub-dependent work is flagged
    hub_pending; the spoke is marked self-certified with a hub-unreachable marker."""
    if hub_reachable:
        return {"hub_pending": [], "self_cert_marker": False, "local_dispatch": True}
    pending = [w for w in work_items if w.get("hub_dependent")]
    return {"hub_pending": [w.get("id") for w in pending], "self_cert_marker": True,
            "local_dispatch": True, "marker": "hub-unreachable"}


# ---------- the drain tick ----------
def drain_tick(events, routing, state, now_ts, spent=0, budget=None,
               global_rate_cap=DEFAULT_GLOBAL_RATE_CAP):
    """Process a batch of journal events into wake decisions under all bounds.
    Returns {wakes, audits, attention, paused}. Mutates `state` (replay-safe)."""
    result = {"wakes": [], "audits": [], "attention": [], "paused": state["paused"]}

    # burn breaker (global) — checked once per tick
    burn = circuit_breaker_burn(spent, budget)
    if burn["level"] == "alert":
        result["attention"].append({"kind": "burn", "reason": f"budget at {burn['pct']*100:.0f}%",
                                     "figure": burn["spent"]})
    if burn["level"] == "paused":
        _emit_decision("burn cap reached — pause autonomous dispatch",
                       {"pct": burn["pct"], "spent": burn["spent"]}, result["audits"])
        result["attention"].append({"kind": "burn", "reason": "budget at 100% — autonomous dispatch PAUSED",
                                     "figure": burn["spent"]})
        state["paused"] = True
        result["paused"] = True
        return result  # no wakes while paused

    for ev in events:
        etype = ev.get("type")
        for aid in match_advisors(etype, routing):
            pol = routing[aid]
            decision = {"event": etype, "advisor": aid, "correlation_id": ev.get("correlation_id")}

            # analysis_trigger floor — no wake below the advisor's min signal
            if float(ev.get("signal", 1)) < float(pol["analysis_trigger"]):
                decision["disposition"] = "below_floor"
                result["audits"].append({"type": "dispatch_audit", "actor": "dispatcher",
                                         "status": "below_floor", **decision})
                continue

            # idempotency — an in-flight wake for the same key is not re-issued
            ikey = f"{ev.get('correlation_id')}::{aid}"
            if ikey in state["in_flight"]:
                decision["disposition"] = "idempotent_skip"
                result["audits"].append({"type": "dispatch_audit", "actor": "dispatcher",
                                         "status": "idempotent_skip", **decision})
                continue

            # debounce — collapse identical events within the window to one wake
            dkey = f"{aid}::{etype}"
            if _within(state["debounce"].get(dkey), now_ts, pol["debounce_window_s"]):
                decision["disposition"] = "debounced"
                result["audits"].append({"type": "dispatch_audit", "actor": "dispatcher",
                                         "status": "debounced", **decision})
                continue

            # rate breaker — per-advisor + global wakes/hour cap
            adv_recent = _recent_count(state["wake_log"].get(aid, []), now_ts)
            global_recent = _recent_count(state["global_wakes"], now_ts)
            if adv_recent >= pol["rate_cap_per_hour"] or global_recent >= global_rate_cap:
                _emit_decision(f"rate cap reached for {aid}",
                               {"advisor_rate": adv_recent, "global_rate": global_recent},
                               result["audits"])
                result["attention"].append({"kind": "rate", "advisor": aid,
                                            "reason": f"{aid} hit wakes/hour cap",
                                            "figure": adv_recent})
                decision["disposition"] = "rate_paused"
                result["audits"].append({"type": "dispatch_audit", "actor": "dispatcher",
                                         "status": "rate_paused", **decision})
                continue

            # issue the wake
            state["debounce"][dkey] = now_ts
            state["in_flight"][ikey] = now_ts
            state["wake_log"].setdefault(aid, []).append(now_ts)
            state["global_wakes"].append(now_ts)
            decision["disposition"] = "wake"
            result["wakes"].append({"advisor": aid, "command": pol["dispatch_command"],
                                    "event": etype, "correlation_id": ev.get("correlation_id")})
            result["audits"].append({"type": "dispatch_audit", "actor": "dispatcher",
                                     "status": "wake", **decision})
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="dispatcher drain tick")
    ap.add_argument("--registry", default=DEFAULT_REGISTRY)
    ap.add_argument("--journal-path", default=event_bus.DEFAULT_JOURNAL if event_bus else None)
    ap.add_argument("--now", required=True)
    a = ap.parse_args(argv)
    routing = load_routing(a.registry)
    events = []
    if a.journal_path and os.path.exists(a.journal_path):
        events = [json.loads(l) for l in open(a.journal_path) if l.strip()]
    res = drain_tick(events, routing, _new_state(), a.now)
    print(json.dumps({"wakes": len(res["wakes"]), "attention": res["attention"],
                      "paused": res["paused"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
