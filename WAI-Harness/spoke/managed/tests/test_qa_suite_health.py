"""Test-at-birth for impl-qa-stale-test-detection-v1 (tools/qa_suite_health.py).

  AC1 stale: a once-green test whose lug last-verification ts is older than
      stale_days is flagged stale; a fresh one is not.
  AC2 test-null: result==null checks are listed in null_checks (disclosed).
  AC3 failing: result==0 checks are listed in failing.
  AC4 gap_summary counts {test_null, stale, failing}; empty -> zeroed-but-valid.
  AC5 wakeup: read_qa_health wired into generate_wakeup_brief as brief['qa_health'].
"""
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import qa_suite_health as qa

NOW = 1_780_000_000.0


def _iso(epoch):
    return qa.datetime.fromtimestamp(epoch, qa.timezone.utc).isoformat()


def _lug(lid, vt, completed_at=None):
    return {"id": lid, "type": "implementation", "status": "completed",
            "schema_version": 4, "acceptance_criteria": ["AC1 x"],
            "verification_test": vt,
            "completed_at": completed_at or _iso(NOW - 3600)}


# --- AC1 -------------------------------------------------------------------

def test_stale_detection_once_green_now_old():
    fresh = _lug("fresh", [{"name": "t", "covers_ac": "AC1", "result": 1,
                            "result_ts": _iso(NOW - 5 * 86400)}])
    old = _lug("old", [{"name": "t", "covers_ac": "AC1", "result": 1,
                        "result_ts": _iso(NOW - 90 * 86400)}])
    h = qa.compute_qa_health([fresh, old], now=NOW, stale_days=60)
    ids = {s["lug_id"] for s in h["stale_tests"]}
    assert "old" in ids
    assert "fresh" not in ids
    assert h["stale_tests"][0]["age_days"] >= 60

    # staleness falls back to the lug's completed_at when the test has no own ts
    old_by_lug = _lug("old2", [{"name": "t", "covers_ac": "AC1", "result": 1}],
                      completed_at=_iso(NOW - 100 * 86400))
    h2 = qa.compute_qa_health([old_by_lug], now=NOW, stale_days=60)
    assert {s["lug_id"] for s in h2["stale_tests"]} == {"old2"}


# --- AC2 -------------------------------------------------------------------

def test_null_checks_disclosed():
    lug = _lug("n", [{"name": "t1", "covers_ac": "AC1", "result": None},
                     {"name": "t2", "covers_ac": "AC2", "result": 1}])
    h = qa.compute_qa_health([lug], now=NOW)
    names = {c["test"] for c in h["null_checks"]}
    assert names == {"t1"}              # only the null one is a disclosed gap
    assert h["gap_summary"]["test_null"] == 1


# --- AC3 -------------------------------------------------------------------

def test_failing_listed():
    lug = _lug("f", [{"name": "boom", "covers_ac": "AC1", "result": 0}])
    h = qa.compute_qa_health([lug], now=NOW)
    assert h["failing"][0]["test"] == "boom"
    assert h["gap_summary"]["failing"] == 1
    # a failing check is not also counted as null or stale
    assert h["gap_summary"]["test_null"] == 0
    assert h["gap_summary"]["stale"] == 0


# --- AC4 -------------------------------------------------------------------

def test_gap_summary_and_graceful_empty():
    lugs = [
        _lug("a", [{"name": "ok", "covers_ac": "AC1", "result": 1, "result_ts": _iso(NOW - 3600)}]),
        _lug("b", [{"name": "nu", "covers_ac": "AC1", "result": None}]),
        _lug("c", [{"name": "st", "covers_ac": "AC1", "result": 1, "result_ts": _iso(NOW - 200 * 86400)}]),
        _lug("d", [{"name": "fa", "covers_ac": "AC1", "result": 0}]),
    ]
    h = qa.compute_qa_health(lugs, now=NOW, stale_days=60)
    assert h["gap_summary"] == {"test_null": 1, "stale": 1, "failing": 1}
    assert h["status"] == "ok"
    # graceful: no v4 lugs -> zeroed-but-valid, never raises
    empty = qa.compute_qa_health([], now=NOW)
    assert empty["gap_summary"] == {"test_null": 0, "stale": 0, "failing": 0}
    assert empty["status"] == "no-v4-lugs-yet"
    # a non-v4 lug is ignored
    legacy = qa.compute_qa_health([{"id": "v3", "schema_version": 3,
                                    "verification_test": [{"result": 0}]}], now=NOW)
    assert legacy["gap_summary"]["failing"] == 0


def test_read_qa_health_graceful_on_empty_spoke(tmp_path):
    (tmp_path / "WAI-Spoke").mkdir()
    h = qa.read_qa_health(str(tmp_path), now=NOW)
    assert h["status"] in ("no-v4-lugs-yet", "ok")
    assert h["gap_summary"]["stale"] == 0


# --- AC5 -------------------------------------------------------------------

def test_wakeup_qa_health_wired(tmp_path):
    spoke = tmp_path / "WAI-Spoke"
    d = spoke / "lugs" / "bytype" / "implementation" / "completed"
    d.mkdir(parents=True)
    (d / "l.json").write_text(json.dumps(_lug(
        "l", [{"name": "st", "covers_ac": "AC1", "result": 1,
               "result_ts": _iso(NOW - 200 * 86400)}])))
    import importlib.util, os
    root = str(Path(__file__).resolve().parents[1])
    spec = importlib.util.spec_from_file_location(
        "gwb_qa", os.path.join(root, "tools", "generate_wakeup_brief.py"))
    gwb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gwb)
    assert hasattr(gwb, "read_qa_health")
    out = gwb.read_qa_health(spoke)
    assert out is not None
    assert "gap_summary" in out
    assert out["gap_summary"]["stale"] == 1
