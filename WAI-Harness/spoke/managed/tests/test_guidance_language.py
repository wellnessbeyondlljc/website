"""Acceptance proof: guidance.py — the guidance language (spec-guidance-language-v1, AC45).
One test per spec test[] case (8) + load/stacking. Hermetic + pure.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import guidance as g  # noqa: E402

NOW = "2026-06-10T12:00:00Z"


def _items():
    return [
        {"id": "l1", "epic": "epic-harness-v4-self-certifying-v1", "target": "v4"},
        {"id": "l2", "epic": "epic-other", "target": "other"},
        {"id": "l3", "initiative": "verifiable-work-contracts", "target": "v4"},
    ]


# spec test 1 — focus-lock exclusive scopes the queue
def test_focus_lock_exclusive_scopes_queue():
    locks = [{"focus_id": "f1", "target": "epic-harness-v4-self-certifying-v1", "mode": "exclusive"}]
    res = g.filter_by_focus(_items(), locks, NOW)
    assert [i["id"] for i in res["dispatch"]] == ["l1"]
    assert [p["item"]["id"] for p in res["paused"]] == ["l2", "l3"]
    assert all(p["reason"] == "paused by focus-lock" for p in res["paused"])


# spec test 2 — budget guardrail blocks when spend exceeds value
def test_guardrail_budget_blocks_over_spend():
    rails = [{"guardrail_id": "g-budget", "kind": "budget", "value": 100, "hard": True}]
    assert g.enforce_guardrail({"spend_after": 80}, rails)["allowed"] is True
    blocked = g.enforce_guardrail({"spend_after": 120}, rails)
    assert blocked["allowed"] is False and blocked["violation"]["kind"] == "budget"


# spec test 3 — no_touch_path blocks an edit, file unchanged (we assert the BLOCK)
def test_guardrail_no_touch_path_blocks():
    rails = [{"guardrail_id": "g-notouch", "kind": "no_touch_path", "value": "infra/*", "hard": True}]
    assert g.enforce_guardrail({"path": "src/app.py"}, rails)["allowed"] is True
    blocked = g.enforce_guardrail({"path": "infra/config.json"}, rails)
    assert blocked["allowed"] is False and blocked["violation"]["kind"] == "no_touch_path"


# spec test 4 — a spoke cannot weaken a mandated hub guardrail
def test_mandated_guardrail_not_weakenable(tmp_path):
    hub = tmp_path / "hub"; spoke = tmp_path / "spoke"
    hub.mkdir(); spoke.mkdir()
    (hub / g.GUIDANCE_FILE).write_text(json.dumps({"guardrails": [
        {"guardrail_id": "g-budget", "kind": "budget", "value": 100, "hard": True}]}))
    (spoke / g.GUIDANCE_FILE).write_text(json.dumps({"guardrails": [
        {"guardrail_id": "g-budget", "kind": "budget", "value": 999, "hard": True}]}))  # weaker
    loaded = g.load_guidance(str(spoke), str(hub))
    rails = {r["guardrail_id"]: r for r in loaded["guardrails"]}
    assert rails["g-budget"]["value"] == 100  # hub value stands
    assert loaded["rejected_guardrails"] and loaded["rejected_guardrails"][0]["guardrail"]["value"] == 999
    # a spoke ADDING a stricter independent rail is accepted
    (spoke / g.GUIDANCE_FILE).write_text(json.dumps({"guardrails": [
        {"guardrail_id": "g-local-notouch", "kind": "no_touch_path", "value": "secrets/*", "hard": True}]}))
    loaded2 = g.load_guidance(str(spoke), str(hub))
    assert any(r["guardrail_id"] == "g-local-notouch" for r in loaded2["guardrails"])


# spec test 5 — sign-off gating: staged until approve; reject returns labelled
def test_sign_off_staged_until_acked():
    drop = {"action_id": "a1", "bucket": "Drop"}
    assert g.needs_sign_off(drop) is True
    assert g.can_proceed(drop, []) is False                       # staged
    assert g.sign_off_status("a1", []) == "staged"
    acks = [{"action_id": "a1", "ack": "approve", "reason": "ok", "signer": "mario"}]
    assert g.can_proceed(drop, acks) is True
    rej = [{"action_id": "a1", "ack": "reject", "reason": "no", "signer": "mario"}]
    assert g.sign_off_status("a1", rej) == "rejected" and g.can_proceed(drop, rej) is False
    # a non-gated action never needs sign-off
    assert g.can_proceed({"action_id": "a2", "bucket": "Preserve"}, []) is True


# spec test 6 — guidance-log records steering with signer + reason
def test_guidance_log_records_steering(tmp_path):
    log = tmp_path / g.LOG_FILE
    g.log_guidance(str(log), {"event": "focus_lock.engaged", "ts": NOW,
                              "signer": "mario", "reason": "ship v4", "focus_id": "f1"})
    g.log_guidance(str(log), {"event": "sign_off.approve", "ts": NOW,
                              "signer": "mario", "reason": "verified", "action_id": "a1"})
    recs = g.read_guidance_log(str(log))
    assert len(recs) == 2
    assert {r["event"] for r in recs} == {"focus_lock.engaged", "sign_off.approve"}
    assert all(r.get("signer") and r.get("reason") for r in recs)  # answers who/why


# spec test 7 — goal ranking reorders the queue by priority
def test_goal_ranking_reorders_queue():
    goals = [{"goal_id": "g-v4", "target": "v4", "priority": 1, "statement": "clear v4"},
             {"goal_id": "g-other", "target": "other", "priority": 5}]
    ranked = g.ranked_items(_items(), goals, NOW)
    # v4-targeted items first (priority 1), other last
    assert [i["id"] for i in ranked][:2] == ["l1", "l3"]
    assert ranked[-1]["id"] == "l2"


# spec test 8 — expired focus-lock auto-releases + is reported
def test_expired_focus_lock_auto_releases():
    locks = [{"focus_id": "f-old", "target": "epic-harness-v4-self-certifying-v1",
              "mode": "exclusive", "active_until": "2026-01-01T00:00:00Z"}]  # past
    res = g.filter_by_focus(_items(), locks, NOW)
    assert "f-old" in res["expired"]
    assert len(res["dispatch"]) == 3 and res["paused"] == []  # no active lock -> all dispatch
