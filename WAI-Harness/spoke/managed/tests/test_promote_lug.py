"""Acceptance proof: promote_lug.py — draft->open promotion gate (AC11/AC12).
A lug promotes only when structurally valid AND its verification_test actually passed;
the run is recorded in test_result_history.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import promote_lug as pl  # noqa: E402

NOW = "2026-06-10T06:00:00Z"


def _valid_draft(result=1):
    """A structurally-valid v4 draft whose single AC is covered by one test."""
    return {
        "id": "impl-demo-v1", "type": "implementation", "status": "draft",
        "schema_version": 4, "rev": 1,
        "title": "Demo", "situation": "an observable condition warranting work",
        "context_snapshot": {"branch": "main"}, "triggering_session": "session-x",
        "acceptance_criteria": ["AC1 the thing works"],
        "verification_test": [{"mode": "mechanical", "result": result,
                               "covers_ac": "AC1", "check_ref": "tests/test_demo.py"}],
    }


def test_promotes_when_valid_and_passing():
    lug = _valid_draft(result=1)
    res = pl.promote(lug, NOW, version="4.0.0-pre")
    assert res["ok"] is True
    out = res["lug"]
    assert out["status"] == "open" and out["updated_at"] == NOW
    hist = out["test_result_history"]
    assert len(hist) == 1 and hist[0]["result"] == pl.PASS and hist[0]["ts"] == NOW
    assert hist[0]["covers"] == ["AC1"]


def test_blocked_when_test_not_run():
    lug = _valid_draft(result=None)  # authored but never run
    res = pl.promote(lug, NOW)
    assert res["ok"] is False
    assert any("not run yet" in f for f in res["failures"])
    assert lug["status"] == "draft"  # unchanged — no silent flip


def test_blocked_when_test_failing():
    lug = _valid_draft(result=0)
    res = pl.promote(lug, NOW)
    assert res["ok"] is False
    assert any("failing" in f for f in res["failures"])
    assert lug["status"] == "draft"


def test_blocked_when_structurally_invalid():
    lug = _valid_draft(result=1)
    del lug["situation"]            # mandatory v4 context field
    res = pl.promote(lug, NOW)
    assert res["ok"] is False
    assert any("situation" in f for f in res["failures"])


def test_blocked_when_ac_uncovered():
    lug = _valid_draft(result=1)
    lug["acceptance_criteria"] = ["AC1 the thing works", "AC2 the other thing"]  # AC2 uncovered
    res = pl.promote(lug, NOW)
    assert res["ok"] is False
    assert any("AC2" in f for f in res["failures"])


def test_record_test_run_appends_history():
    lug = _valid_draft(result=1)
    pl.record_test_run(lug, "mechanical", pl.PASS, NOW, version="4.0.0-pre", covers=["AC1"])
    pl.record_test_run(lug, "attested", pl.PASS, "2026-06-10T07:00:00Z")
    assert len(lug["test_result_history"]) == 2
    assert lug["test_result_history"][1]["mode"] == "attested"
