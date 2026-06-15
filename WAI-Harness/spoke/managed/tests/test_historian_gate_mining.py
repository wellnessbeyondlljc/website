#!/usr/bin/env python3
"""Verification test for impl-historian-gate-mining-v1 (test-at-birth).

Covers verify[]: trigger honored (skip below MIN_FLOOR, run at EVENTS_FLOOR),
recurring-halt candidate, bubble-up to hub incoming with attribution (and NOT
self-adopted), regression alert, Pattern Health section, and loop closure
(version-anchored pre/post measurement). Also checks SKILL.md declares the
trigger and scan_state carries the cursor.
"""
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


H = _load("historian_gate_mine")


def test_trigger_skips_thin_data_runs_on_sufficient():
    # below MIN_FLOOR -> skipped, with an observable reason (no over-cycling)
    skip = H.evaluate_trigger(new_events=4, sessions_since=1)
    assert skip["run"] is False and "MIN_FLOOR" in skip["reason"]
    # at/above EVENTS_FLOOR -> runs
    run = H.evaluate_trigger(new_events=60, sessions_since=0)
    assert run["run"] is True and "EVENTS_FLOOR" in run["reason"]
    # time-based path: enough sessions even if events between MIN and EVENTS floor
    run2 = H.evaluate_trigger(new_events=20, sessions_since=5)
    assert run2["run"] is True and "SESSIONS_FLOOR" in run2["reason"]
    # between floors with too few sessions -> wait
    wait = H.evaluate_trigger(new_events=20, sessions_since=2)
    assert wait["run"] is False


def test_recurring_halt_produces_one_candidate():
    events = [{"flow_id": "closeout", "step_id": "commit", "disposition": "halted",
               "session_id": f"s{i}"} for i in range(3)]
    events += [{"flow_id": "closeout", "step_id": "commit", "disposition": "approved",
                "session_id": "s9", "attempt": 2}]
    found = H.mine(events)
    rec = found["recurring_halts"]
    assert len(rec) == 1, f"exactly one recurring-halt candidate, got {len(rec)}"
    assert rec[0]["flow_id"] == "closeout" and rec[0]["step_id"] == "commit"
    assert rec[0]["session_count"] == 3
    # halted in only 2 sessions -> NOT a candidate
    thin = H.mine([{"flow_id": "x", "step_id": "y", "disposition": "halted", "session_id": s}
                   for s in ("a", "b")])
    assert thin["recurring_halts"] == []


def test_regression_alert_on_version_bounded_drop():
    events = []
    # v1: 9/10 approved = 0.9
    for i in range(9):
        events.append({"flow_id": "f", "flow_version": 1, "disposition": "approved", "attempt": 1})
    events.append({"flow_id": "f", "flow_version": 1, "disposition": "escalate"})
    # v2: 5/10 approved = 0.5  -> 40% drop > 15%
    for i in range(5):
        events.append({"flow_id": "f", "flow_version": 2, "disposition": "approved", "attempt": 1})
    for i in range(5):
        events.append({"flow_id": "f", "flow_version": 2, "disposition": "escalate"})
    found = H.mine(events)
    assert len(found["regressions"]) == 1
    r = found["regressions"][0]
    assert r["from_version"] == 1 and r["to_version"] == 2 and r["approval_drop"] > 0.15


def test_calibration_over_strict_and_too_loose():
    over = [{"flow_id": "f", "step_id": "s", "disposition": "halted", "session_id": f"x{i}"}
            for i in range(9)] + [{"flow_id": "f", "step_id": "s", "disposition": "approved"}]
    cal = H.mine(over)["calibration"]
    assert any(c["signal"] == "over-strict" for c in cal), "halt rate >80% -> over-strict"
    loose = [{"flow_id": "g", "step_id": "t", "disposition": "approved",
              "evidence": {"downstream_failed": True}}]
    cal2 = H.mine(loose)["calibration"]
    assert any(c["signal"] == "too-loose" for c in cal2), "approved-then-downstream-fail -> too-loose"


def test_bubble_up_to_hub_not_self_adopted(tmp_path):
    hub_incoming = str(tmp_path / "hub_incoming")
    candidate = {"type": "recurring_halt", "flow_id": "closeout", "step_id": "commit",
                 "session_count": 4}
    p = H.bubble_up(candidate, hub_incoming, fleet_worthy=True)
    assert p and os.path.exists(p)
    lug = json.load(open(p))
    assert lug["routed_to"] == "hub" and lug["type"] == "change"
    assert lug["self_adopted_locally"] is False, "spoke must NOT self-adopt"
    assert lug.get("resolve_attribution") and lug.get("kind"), "external-session attribution present"
    # a local-only quirk is NOT delivered to the hub
    assert H.bubble_up(candidate, hub_incoming, fleet_worthy=False) is None


def test_pattern_health_section_renders_metrics_and_trigger_flag():
    events = [{"flow_id": "closeout", "disposition": "approved", "attempt": 1},
              {"flow_id": "closeout", "disposition": "escalate"},
              {"flow_id": "closeout", "step_id": "commit", "disposition": "halted"}]
    health = H.pattern_health(events, open_candidates=[1, 2], trigger_fired=True)
    assert "first_attempt_approval_rate" in health and "closeout" in health["first_attempt_approval_rate"]
    assert health["halt_frequency_per_step"]["closeout/commit"] == 1
    assert health["open_candidates"] == 2
    assert health["trigger_fired"] is True


def test_loop_closure_measures_pre_post():
    post = [{"flow_id": "f", "disposition": "approved"} for _ in range(9)] + \
           [{"flow_id": "f", "disposition": "halted"}]  # 10% halt now
    res = H.close_loop(pre_baseline_rate=0.5, post_events=post, flow_id="f")
    assert res["post_adoption_halt_rate"] == 0.1
    assert res["improved"] is True, "post halt rate < pre baseline -> improved"


def test_skill_declares_trigger_and_scan_state_has_cursor():
    skill = os.path.join(ROOT, "WAI-Spoke/advisors/historian/SKILL.md")
    assert os.path.exists(skill)
    body = open(skill).read()
    for token in ("EVENTS_FLOOR", "SESSIONS_FLOOR", "MIN_FLOOR", "bubble up", "does not self-adopt"):
        assert token.lower() in body.lower(), f"SKILL.md must document {token}"
    ss = json.load(open(os.path.join(ROOT, "WAI-Spoke/advisors/historian/scan_state.json")))
    assert "last_mined_at" in ss and "gate_mining_trigger" in ss and "gate_mining_floors" in ss


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn) and name != "test_bubble_up_to_hub_not_self_adopted":
            fn(); print(f"PASS {name}")
    print("ALL PASS (run via pytest for tmp_path fixtures)")
