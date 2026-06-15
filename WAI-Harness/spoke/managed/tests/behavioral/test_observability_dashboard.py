"""Test-at-birth for impl-observability-dashboard-surface-v1.

Covers the 4 acceptance criteria of the observability oversight surfaces:
  AC1 confidence model: three questions, each surface-backed + answerable flag;
      non-answerable questions listed in observability_defects[].
  AC2 now surface: queue_depth (per type x status), advisor roster, recent_activity;
      missing source degrades to empty without raising.
  AC3 attention surface: rollback + stalled-2x lug + human sign-off, each with a
      reason and a priority (severity x age); overloaded past max_depth.
  AC4 freshness contracts: source older than cadence (or absent) -> STALE badge
      with age; fresh-within-cadence -> no badge.
"""
import json
import os
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import observability_dashboard as obs


# fixed reference clock for deterministic freshness
NOW = 1_780_000_000.0  # arbitrary epoch
ISO = obs.datetime.fromtimestamp


def _iso(epoch):
    return obs.datetime.fromtimestamp(epoch, obs.timezone.utc).isoformat()


@pytest.fixture
def spoke(tmp_path):
    """A minimal fixture spoke with one normal lug, one stalled lug, a recent
    rollback, an advisor, a human-gated savepoint, and a recent track entry."""
    root = tmp_path / "WAI-Spoke"
    # lugs: two open implementation lugs (one stalled)
    impl_open = root / "lugs" / "bytype" / "implementation" / "open"
    impl_open.mkdir(parents=True)
    (impl_open / "normal.json").write_text(json.dumps({
        "id": "impl-normal", "type": "implementation", "status": "open",
        "updated_at": _iso(NOW - 100)}))
    (impl_open / "stalled.json").write_text(json.dumps({
        "id": "impl-stalled", "type": "implementation", "status": "open",
        "autopilot_failures": 2, "updated_at": _iso(NOW - 2 * 86400)}))
    # a task lug too (queue_depth must key per type x status)
    task_open = root / "lugs" / "bytype" / "task" / "open"
    task_open.mkdir(parents=True)
    (task_open / "t.json").write_text(json.dumps({"id": "task-1", "type": "task", "status": "open"}))

    # advisor scan_state
    adv = root / "advisors" / "archie"
    adv.mkdir(parents=True)
    (adv / "scan_state.json").write_text(json.dumps({
        "advisor_id": "archie", "status": "active", "activation": "all_spoke_types"}))

    # lifecycle: one recent rollback (in window) + one ancient (out of window)
    (root / "advisors" / "lifecycle.jsonl").write_text(
        json.dumps({"advisor_id": "backup-adv", "event_type": "auto_rolled_back",
                    "ts": _iso(NOW - 600), "reason": "Act rate dropped 100%->0%"}) + "\n" +
        json.dumps({"advisor_id": "old-adv", "event_type": "auto_rolled_back",
                    "ts": _iso(NOW - 30 * 86400), "reason": "ancient"}) + "\n")

    # human-gated active savepoint
    sp = root / "savepoints"
    sp.mkdir(parents=True)
    (sp / "sp1.json").write_text(json.dumps({
        "id": "sp-cutover", "status": "active", "claimed_at": _iso(NOW - 3600),
        "blockers_and_human_gates": [{"gate": "Phase-5 cutover teardown",
                                      "owner": "human/Mario"}]}))

    # current session track with a recent entry
    sess = root / "sessions" / "session-x"
    sess.mkdir(parents=True)
    (sess / "track.jsonl").write_text(
        json.dumps({"event": "turn", "ts": _iso(NOW - 120)}) + "\n")

    return str(tmp_path)


# --- AC1 -------------------------------------------------------------------

def test_confidence_three_questions_answerable(spoke):
    d = obs.build_dashboard(spoke, now_ts=NOW)
    conf = d["confidence"]
    assert set(conf) == {"what_is_happening", "is_it_on_track", "what_needs_me"}
    for q in conf.values():
        assert q["surface"] in d["surfaces"]
        assert isinstance(q["answerable"], bool)
    # now + attention have fresh sources -> answerable
    assert conf["what_is_happening"]["answerable"] is True
    assert conf["what_needs_me"]["answerable"] is True
    # on_track has no fresh test data (empty) -> unanswerable -> a recorded defect
    assert conf["is_it_on_track"]["answerable"] is False
    assert "is_it_on_track" in d["observability_defects"]


# --- AC2 -------------------------------------------------------------------

def test_now_surface_queue_and_advisors(spoke):
    d = obs.build_dashboard(spoke, now_ts=NOW)
    now = d["surfaces"]["now"]
    assert now["queue_depth"]["implementation"]["open"] == 2
    assert now["queue_depth"]["task"]["open"] == 1
    assert now["queue_total"] == 3
    assert now["advisor_count"] == 1
    assert now["advisors"][0]["id"] == "archie"
    assert now["advisors"][0]["status"] == "active"
    assert now["recent_activity"]["last_1h"] == 1
    assert now["recent_activity"]["last_24h"] == 1


def test_now_surface_missing_sources_degrade(tmp_path):
    # an empty spoke must not raise; surfaces come back empty
    (tmp_path / "WAI-Spoke").mkdir()
    d = obs.build_dashboard(str(tmp_path), now_ts=NOW)
    now = d["surfaces"]["now"]
    assert now["queue_total"] == 0
    assert now["advisor_count"] == 0
    assert now["queue_depth"] == {}


# --- AC3 -------------------------------------------------------------------

def test_attention_surface_items_reasons_priority(spoke):
    d = obs.build_dashboard(spoke, now_ts=NOW)
    att = d["surfaces"]["attention"]
    by_source = {i["source"]: i for i in att["items"]}
    # all three expected sources present
    assert "lifecycle" in by_source   # the recent rollback
    assert "lug" in by_source         # the stalled-2x lug
    assert "savepoint" in by_source   # the human sign-off gate
    # the ancient rollback was windowed out (only the recent one survives)
    assert sum(1 for i in att["items"] if i["source"] == "lifecycle") == 1
    # each item carries a reason and a positive priority
    for it in att["items"]:
        assert it["reason"]
        assert it["priority"] > 0
    # priority = severity * (1 + age_days): the 2-day stalled lug outranks the
    # fresher rollback despite rollback's higher base severity? verify ordering is
    # by computed priority (sorted desc) and reflects age weighting
    priorities = [i["priority"] for i in att["items"]]
    assert priorities == sorted(priorities, reverse=True)
    assert att["overloaded"] is False


def test_attention_overloaded_alarm(tmp_path):
    root = tmp_path / "WAI-Spoke"
    d = root / "lugs" / "bytype" / "implementation" / "open"
    d.mkdir(parents=True)
    for i in range(obs.ATTENTION_MAX_DEPTH + 1):
        (d / f"s{i}.json").write_text(json.dumps({
            "id": f"impl-{i}", "type": "implementation", "status": "open",
            "needs_attention": "blocked", "updated_at": _iso(NOW - 60)}))
    dash = obs.build_dashboard(str(tmp_path), now_ts=NOW)
    att = dash["surfaces"]["attention"]
    assert att["count"] == obs.ATTENTION_MAX_DEPTH + 1
    assert att["overloaded"] is True


# --- AC4 -------------------------------------------------------------------

def test_freshness_stale_and_fresh_badges():
    # fresh: source 60s old, cadence 300s -> no badge
    fresh = obs.freshness(NOW - 60, 300, NOW)
    assert fresh["fresh"] is True
    assert fresh["badge"] is None
    # stale: source 2h old, cadence 300s -> STALE badge with age
    stale = obs.freshness(NOW - 7200, 300, NOW)
    assert stale["fresh"] is False
    assert stale["badge"].startswith("STALE (")
    assert "2h" in stale["badge"]
    # absent source -> STALE (no data), emptiness made visible
    none_src = obs.freshness(None, 300, NOW)
    assert none_src["fresh"] is False
    assert none_src["badge"] == "STALE (no data)"


def test_on_track_stale_when_no_test_data(spoke):
    # the fixture has no harness.db/test_results and no completed lugs -> on_track
    # surface is STALE (its emptiness is visible, not silently 'current')
    d = obs.build_dashboard(spoke, now_ts=NOW)
    ot = d["surfaces"]["on_track"]
    assert ot["freshness"]["fresh"] is False
    assert ot["freshness"]["badge"] is not None
    assert ot["certification"]["test_results"]["total"] == 0
