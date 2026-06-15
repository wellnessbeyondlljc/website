#!/usr/bin/env python3
"""Verification test for impl-scheduler-dispatcher-v1 (test-at-birth).

Covers verify[]: routing (only subscribed advisors wake), debounce, idempotency,
rate breaker, burn breaker (80% alert / 100% pause), loop guard, gate-retry
orchestration + 2-cycle cap, liveness requeue, hub-down local-continue + self-
cert marker, and the dispatcher self-gate (every decision -> dispatch_audit).
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


D = _load("dispatcher")


def _routing(**over):
    base = {"expediter": {"subscribes_to": ["lug_mutation"], "debounce_window_s": 300,
                          "max_concurrency": 1, "analysis_trigger": 0, "rate_cap_per_hour": 5,
                          "dispatch_command": "python3 tools/expediter.py"},
            "archie":    {"subscribes_to": ["architecture_drift"], "debounce_window_s": 60,
                          "max_concurrency": 1, "analysis_trigger": 0, "rate_cap_per_hour": 5,
                          "dispatch_command": "python3 tools/archie.py"}}
    base["expediter"].update(over)
    return base


def _ev(t="lug_mutation", cid="c1", **kw):
    return {"type": t, "correlation_id": cid, "ts": "2026-06-09T00:00:00Z", **kw}


def test_routing_only_subscribed_advisor_wakes():
    routing = _routing()
    assert D.match_advisors("lug_mutation", routing) == ["expediter"]
    assert D.match_advisors("architecture_drift", routing) == ["archie"]
    res = D.drain_tick([_ev()], routing, D._new_state(), "2026-06-09T00:00:00Z")
    assert [w["advisor"] for w in res["wakes"]] == ["expediter"], "only subscribed advisor wakes"


def test_debounce_collapses_to_one_wake():
    routing = _routing(debounce_window_s=300)
    st = D._new_state()
    events = [_ev(cid=f"c{i}") for i in range(20)]  # 20 lug_mutations within the window
    res = D.drain_tick(events, routing, st, "2026-06-09T00:00:10Z")
    assert len([w for w in res["wakes"] if w["advisor"] == "expediter"]) == 1, "exactly one wake"


def test_idempotency_no_second_wake_while_in_flight():
    routing = _routing(debounce_window_s=0)  # disable debounce to isolate idempotency
    st = D._new_state()
    D.drain_tick([_ev(cid="same")], routing, st, "2026-06-09T00:00:00Z")
    res = D.drain_tick([_ev(cid="same")], routing, st, "2026-06-09T00:10:00Z")
    assert not res["wakes"], "in-flight idempotency key must not re-wake"
    assert any(a["status"] == "idempotent_skip" for a in res["audits"])


def test_rate_breaker_pauses_and_raises_attention():
    routing = _routing(debounce_window_s=0, rate_cap_per_hour=3)
    st = D._new_state()
    # 3 distinct wakes fill the cap...
    for i in range(3):
        D.drain_tick([_ev(cid=f"c{i}")], routing, st, "2026-06-09T00:00:00Z")
    res = D.drain_tick([_ev(cid="c9")], routing, st, "2026-06-09T00:00:00Z")
    assert any(a["kind"] == "rate" for a in res["attention"]), "rate breaker raises Attention"
    assert not res["wakes"]


def test_burn_breaker_alert_then_pause():
    routing = _routing()
    assert D.circuit_breaker_burn(80, 100)["level"] == "alert"
    assert D.circuit_breaker_burn(100, 100)["level"] == "paused"
    # at 100% the tick pauses autonomous dispatch + raises Attention + logs a decision
    res = D.drain_tick([_ev()], routing, D._new_state(), "2026-06-09T00:00:00Z",
                       spent=100, budget=100)
    assert res["paused"] and not res["wakes"]
    assert any(a["kind"] == "burn" for a in res["attention"])
    assert any(a.get("type") == "decision" for a in res["audits"]), "pause logged as a decision (WHY on the bus)"


def test_loop_guard_breaks_after_k():
    st = D._new_state()
    broke = [D.loop_guard("expediter::trigger", st, k=3) for _ in range(4)]
    assert broke == [False, False, False, True], "circuit breaks after K re-emits"


def test_gate_retry_orchestration_and_cap():
    # halted attempt 1 -> redispatch at attempt 2 via a write-authorized executor
    r1 = D.gate_retry({"disposition": "halted", "attempt": 1, "flow_id": "closeout", "step_id": "commit"})
    assert r1["action"] == "redispatch" and r1["attempt"] == 2
    assert "executor" in r1, "the gate never writes; an executor does the retry"
    # halted attempt 2 -> still redispatch at 3? no: cap=2 means attempt>=3 escalates
    r2 = D.gate_retry({"disposition": "halted", "attempt": 3})
    assert r2["action"] == "escalate", "2-cycle cap exhausted -> escalate"
    # explicit escalate disposition always escalates
    assert D.gate_retry({"disposition": "escalate", "attempt": 1})["action"] == "escalate"


def test_liveness_requeues_silent_advisor():
    st = D._new_state()
    st["heartbeats"]["expediter"] = "2026-06-09T00:00:00Z"
    stale = D.check_liveness(st, "2026-06-09T00:10:00Z", silence_s=300)  # 10m > 5m
    assert "expediter" in stale, "an advisor silent >5m is flagged for requeue + Attention"
    fresh = D.check_liveness(st, "2026-06-09T00:02:00Z", silence_s=300)  # 2m < 5m
    assert "expediter" not in fresh


def test_hub_down_local_continue_and_self_cert_marker():
    work = [{"id": "w1", "hub_dependent": True}, {"id": "w2", "hub_dependent": False}]
    down = D.hub_status(False, work)
    assert down["local_dispatch"] is True
    assert down["hub_pending"] == ["w1"], "hub-dependent work flagged hub_pending"
    assert down["self_cert_marker"] is True and down["marker"] == "hub-unreachable"
    up = D.hub_status(True, work)
    assert up["self_cert_marker"] is False and up["hub_pending"] == []


def test_dispatcher_self_gates_every_decision():
    routing = _routing()
    res = D.drain_tick([_ev(), _ev(t="architecture_drift", cid="c2")], routing,
                       D._new_state(), "2026-06-09T00:00:00Z")
    audits = [a for a in res["audits"] if a.get("type") == "dispatch_audit"]
    assert len(audits) >= 2, "every routing decision emits a dispatch_audit (self-gate)"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASS")
