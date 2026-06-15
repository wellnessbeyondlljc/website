"""Tests for the verify-before-action gate in tools/ozi_headless.py.

The gate runs lease-check + preconditions + two-pass QC before a lug is
actioned. QC errors BLOCK; warnings advise. A live lease held by another
session causes a skip.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lug_lease  # noqa: E402
from ozi_headless import OziHeadlessRunner  # noqa: E402


CLEAN_LUG = {
    "id": "impl-clean-v1",
    "type": "implementation",
    "status": "open",
    "title": "A clean dispatchable lug",
    "perceive": ["read the thing"],
    "execute": {"steps": ["do the thing"]},
    "verify": {"done_when": ["thing is done"]},
    "effort": "S",
    "model_fit": "haiku",
    "target_files": ["tools/lug_lease.py -- MODIFY"],
}

MALFORMED_LUG = {
    "id": "impl-malformed-v1",
    "type": "implementation",
    "status": "open",
    "title": "Missing PEV lug",
    # no perceive/execute/verify -> Pass 1 errors
}


def _runner(tmp_path):
    spoke = tmp_path
    (spoke / "WAI-Spoke" / "runtime").mkdir(parents=True)
    return OziHeadlessRunner(spoke_path=spoke, budget=3, dry_run=True)


def _write_lug(spoke: Path, lug: dict) -> Path:
    open_dir = spoke / "WAI-Spoke" / "lugs" / "bytype" / "implementation" / "open"
    open_dir.mkdir(parents=True, exist_ok=True)
    p = open_dir / f"{lug['id']}.json"
    p.write_text(json.dumps(lug, indent=2))
    return p


def test_clean_lug_passes_gate(tmp_path):
    r = _runner(tmp_path)
    p = _write_lug(tmp_path, CLEAN_LUG)
    lug = dict(CLEAN_LUG, _lug_path=str(p))
    ok, reason = r._verify_before_action_gate(lug)
    assert ok is True, reason


def test_malformed_lug_blocked_by_qc(tmp_path):
    r = _runner(tmp_path)
    p = _write_lug(tmp_path, MALFORMED_LUG)
    lug = dict(MALFORMED_LUG, _lug_path=str(p))
    ok, reason = r._verify_before_action_gate(lug)
    assert ok is False
    assert reason.startswith("QC error")


def test_live_lease_by_other_session_blocks(tmp_path):
    r = _runner(tmp_path)
    p = _write_lug(tmp_path, CLEAN_LUG)
    # Another session holds a live lease.
    store = r._claims_store()
    assert lug_lease.claim(CLEAN_LUG["id"], "other-session", store_path=store) is True
    lug = dict(CLEAN_LUG, _lug_path=str(p))
    ok, reason = r._verify_before_action_gate(lug)
    assert ok is False
    assert "leased" in reason


def test_unmet_file_precondition_blocks(tmp_path):
    r = _runner(tmp_path)
    p = _write_lug(tmp_path, CLEAN_LUG)
    lug = dict(CLEAN_LUG, _lug_path=str(p),
               preconditions=["file:/nonexistent/path/to/thing.json"])
    ok, reason = r._verify_before_action_gate(lug)
    assert ok is False
    assert "precondition unmet" in reason


def test_gate_filters_blocked_lugs_from_eligible(tmp_path):
    r = _runner(tmp_path)
    _write_lug(tmp_path, CLEAN_LUG)
    _write_lug(tmp_path, MALFORMED_LUG)
    eligible = r._load_eligible_lugs()
    ids = {l.get("id") for l in eligible}
    assert "impl-clean-v1" in ids
    assert "impl-malformed-v1" not in ids
    # A gate-decision event was logged for the blocked lug.
    decisions = [e for e in r.events if e.get("type") == "gate_decision"]
    blocked = [e for e in decisions if e.get("verdict") == "BLOCK"]
    assert any(e["lug_id"] == "impl-malformed-v1" for e in blocked)
