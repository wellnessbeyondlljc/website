"""Acceptance proof: advisor_template_v4.py — v4 advisor template model (AC15)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import advisor_template_v4 as at  # noqa: E402

NOW = "2026-06-10T06:30:00Z"


def _valid():
    return {
        "advisor_id": "ozi", "owned_files": ["advisors/ozi/state.json"],
        "owned_data": ["lugs/"], "schedule": "event-driven",
        "escalation_path": "hub:octo",
        "analysis_trigger": {"type": "data_volume", "threshold": 10, "minimum_floor_seconds": 3600},
    }


def test_valid_advisor_passes():
    assert at.validate_advisor_v4(_valid())["ok"] is True


def test_missing_analysis_trigger_fails():
    d = _valid(); del d["analysis_trigger"]
    res = at.validate_advisor_v4(d)
    assert res["ok"] is False and any("analysis_trigger" in f for f in res["failures"])


def test_missing_owned_files_fails():
    d = _valid(); d["owned_files"] = []
    res = at.validate_advisor_v4(d)
    assert res["ok"] is False and any("owned_files" in f for f in res["failures"])


def test_bad_trigger_type_fails():
    d = _valid(); d["analysis_trigger"]["type"] = "whenever"
    assert at.validate_advisor_v4(d)["ok"] is False


def test_data_volume_trigger_fires_on_threshold():
    trig = {"type": "data_volume", "threshold": 10, "minimum_floor_seconds": 0}
    assert at.trigger_fires(trig, signal_count=10, seconds_since_last=5) is True
    assert at.trigger_fires(trig, signal_count=9, seconds_since_last=5) is False


def test_data_volume_floor_prevents_thrash():
    trig = {"type": "data_volume", "threshold": 1, "minimum_floor_seconds": 3600}
    assert at.trigger_fires(trig, signal_count=100, seconds_since_last=60) is False   # below floor
    assert at.trigger_fires(trig, signal_count=100, seconds_since_last=3600) is True


def test_time_since_last_floor_is_hard_minimum():
    # threshold 3600 but floor 7200 -> fires only after the 2h floor
    trig = {"type": "time_since_last", "threshold": 3600, "minimum_floor_seconds": 7200}
    assert at.trigger_fires(trig, seconds_since_last=3600) is False
    assert at.trigger_fires(trig, seconds_since_last=7200) is True
    # never-run (None) is treated as +inf -> fires
    assert at.trigger_fires(trig, seconds_since_last=None) is True


def test_scan_state_is_recorded(tmp_path):
    p = tmp_path / "scan_state.jsonl"
    at.record_scan_state(str(p), "ozi", True, {"signal_count": 12, "threshold": 10}, NOW)
    at.record_scan_state(str(p), "ozi", False, {"reason": "below floor"}, NOW)
    recs = [json.loads(l) for l in p.read_text().splitlines()]
    assert len(recs) == 2 and recs[0]["fired"] is True and recs[1]["fired"] is False
    assert recs[0]["evidence"]["signal_count"] == 12


def test_ensure_patterns_dir(tmp_path):
    root = tmp_path / "advisors" / "ozi"
    root.mkdir(parents=True)
    d = at.ensure_patterns_dir(str(root))
    assert Path(d).is_dir() and Path(d).name == "patterns"
