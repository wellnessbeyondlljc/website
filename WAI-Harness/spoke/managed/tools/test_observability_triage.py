"""Test-at-birth for the 'what needs me' human-vs-automatable triage lens
(observability_dashboard.py disposition classifier + needs_you/automatable split).

Reinforces the existing attention surface: each item is classified human (only the
user can resolve) vs automatable (an agent can run), so 'what needs me' shows ONLY
the user's to-do and the automatable items are pipeline visibility.
"""
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import observability_dashboard as obs

NOW = 1_780_000_000.0


def _iso(e):
    return obs.datetime.fromtimestamp(e, obs.timezone.utc).isoformat()


def test_classify_disposition_rules():
    assert obs.classify_disposition("sign_off") == "human"
    assert obs.classify_disposition("escalation") == "human"
    assert obs.classify_disposition("rollback") == "automatable"          # self-heal
    # a stalled lug that can self-run -> automatable
    assert obs.classify_disposition("stalled", "autopilot stalled",
                                    {"model_fit": "haiku", "execution_mode": "subagent"}) == "automatable"
    # a lug gated on a human / cutover -> human
    assert obs.classify_disposition("stalled", "x", {"human_gate": True}) == "human"
    assert obs.classify_disposition("stalled", "x", {"blocked_by": ["cutover-signoff"]}) == "human"
    # reason text mentioning a human signal -> human
    assert obs.classify_disposition("stalled", "needs your decision on activation") == "human"


def test_attention_splits_needs_you_vs_automatable(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    # a human-gated savepoint -> needs_you
    (spoke / "savepoints").mkdir(parents=True)
    (spoke / "savepoints" / "sp.json").write_text(json.dumps({
        "id": "sp-cut", "status": "active", "claimed_at": _iso(NOW - 3600),
        "blockers_and_human_gates": [{"gate": "cutover teardown", "owner": "human/Mario"}]}))
    # a stalled, self-runnable lug -> automatable
    d = spoke / "lugs" / "bytype" / "implementation" / "open"
    d.mkdir(parents=True)
    (d / "auto.json").write_text(json.dumps({
        "id": "impl-auto", "type": "implementation", "status": "open",
        "autopilot_failures": 2, "model_fit": "haiku", "execution_mode": "subagent",
        "updated_at": _iso(NOW - 7200)}))
    # a human-flagged open lug (scan d) -> needs_you
    (d / "human.json").write_text(json.dumps({
        "id": "impl-human", "type": "implementation", "status": "open",
        "human_gate": True, "title": "decide activation order", "updated_at": _iso(NOW - 60)}))

    att = obs.build_attention_surface(spoke, NOW)
    ny = {i["subject_ref"] for i in att["needs_you"]}
    au = {i["subject_ref"] for i in att["automatable"]}
    assert "sp-cut" in ny and "impl-human" in ny       # human-only bucket
    assert "impl-auto" in au                            # pipeline bucket
    assert "impl-auto" not in ny
    assert att["needs_you_count"] == 2 and att["automatable_count"] == 1
    # every item carries a disposition
    assert all(i["disposition"] in ("human", "automatable") for i in att["items"])


def test_dashboard_what_needs_me_points_at_needs_you(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    (spoke / "lugs" / "bytype").mkdir(parents=True)
    d = obs.build_dashboard(str(tmp_path), now_ts=NOW)
    assert d["confidence"]["what_needs_me"]["bucket"] == "needs_you"
    assert "needs_you" in d["surfaces"]["attention"]
    assert "automatable" in d["surfaces"]["attention"]


def test_overloaded_counts_only_human_items(tmp_path):
    # many automatable stalled lugs must NOT trip the human-overload alarm
    spoke = tmp_path / "WAI-Spoke"
    d = spoke / "lugs" / "bytype" / "task" / "open"
    d.mkdir(parents=True)
    for i in range(obs.ATTENTION_MAX_DEPTH + 3):
        (d / f"t{i}.json").write_text(json.dumps({
            "id": f"task-{i}", "type": "task", "status": "open",
            "autopilot_failures": 2, "model_fit": "haiku", "execution_mode": "subagent",
            "updated_at": _iso(NOW - 60)}))
    att = obs.build_attention_surface(spoke, NOW)
    assert att["automatable_count"] >= obs.ATTENTION_MAX_DEPTH + 3
    assert att["needs_you_count"] == 0
    assert att["overloaded"] is False        # overload is about HUMAN load, not pipeline depth
