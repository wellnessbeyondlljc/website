"""Tests for tools/verify_engine.py — tiered verification + pattern certification."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import verify_engine  # noqa: E402


def test_mechanical_pass():
    item = {"lug_id": "lug-m", "verify": {"mode": "mechanical", "assertion": "true"}}
    r = verify_engine.verify_mechanical(item)
    assert r["result"] == "pass"
    assert r["mode"] == "mechanical"


def test_mechanical_fail():
    item = {"lug_id": "lug-m", "verify": {"mode": "mechanical", "assertion": "false"}}
    r = verify_engine.verify_mechanical(item)
    assert r["result"] == "fail"


def test_mechanical_no_assertion_fails():
    item = {"lug_id": "lug-m", "verify": {"mode": "mechanical"}}
    r = verify_engine.verify_mechanical(item)
    assert r["result"] == "fail"


def test_attested_is_pending_not_faked():
    item = {"lug_id": "lug-a", "verify": {"mode": "attested", "verifier": "lug-reviewer"}}
    r = verify_engine.verify_attested(item)
    assert r["result"] == "pending"
    assert r["verified_by"] == "lug-reviewer"
    assert r["note"] == "attested-pending"


def test_human_enqueues(tmp_path):
    q = tmp_path / "human_sign_queue.jsonl"
    item = {"lug_id": "lug-h", "verify": {"mode": "human"}}
    r = verify_engine.verify_human(item, queue_path=q)
    assert r["result"] == "pending"
    assert q.exists()
    lines = q.read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["lug_id"] == "lug-h"


def test_aggregate_certified_only_when_all_pass():
    assert verify_engine.aggregate([{"result": "pass"}, {"result": "pass"}]) == "certified"
    assert verify_engine.aggregate([{"result": "pass"}, {"result": "pending"}]) == "partial"
    assert verify_engine.aggregate([{"result": "pass"}, {"result": "fail"}]) == "partial"
    assert verify_engine.aggregate([]) == "partial"


def _make_spoke(tmp_path):
    wai = tmp_path / "WAI-Spoke"
    (wai / "patterns" / "bytype" / "pattern" / "active").mkdir(parents=True)
    (wai / "runtime").mkdir(parents=True)
    return tmp_path


def test_certify_three_mode_pattern_is_partial(tmp_path):
    """3-item pattern (mechanical pass, attested, human) -> partial (not all pass)."""
    spoke = _make_spoke(tmp_path)
    pattern = {
        "id": "pattern-test-v1",
        "version": "1.0.0",
        "title": "Test pattern",
        "initiative_id": "init-x",
        "provenance": {"input_lugs": ["lug-1"]},
        "items": [
            {"lug_id": "lug-1", "verify": {"mode": "mechanical", "assertion": "true"}, "status": "pending"},
            {"lug_id": "lug-2", "verify": {"mode": "attested", "verifier": "lug-reviewer"}, "status": "pending"},
            {"lug_id": "lug-3", "verify": {"mode": "human"}, "status": "pending"},
        ],
        "lifecycle_state": "active",
    }
    bolt = verify_engine.certify_pattern(pattern, spoke, session_id="sess-1", git_sha="abcd1234")
    assert bolt["certification_status"] == "partial"
    by_lug = {i["lug_id"]: i for i in bolt["items"]}
    assert by_lug["lug-1"]["result"] == "pass"
    assert by_lug["lug-2"]["result"] == "pending"
    assert by_lug["lug-3"]["result"] == "pending"
    # Provenance carried forward.
    assert bolt["provenance"]["input_lugs"] == ["lug-1"]
    # Bolt written to recorded/.
    bolt_path = Path(bolt["_bolt_path"])
    assert bolt_path.exists()
    assert bolt_path.parent.name == "recorded"


def test_certify_all_mechanical_pass_is_certified(tmp_path):
    spoke = _make_spoke(tmp_path)
    pattern = {
        "id": "pattern-all-pass-v1",
        "version": "1.0.0",
        "items": [
            {"lug_id": "lug-1", "verify": {"mode": "mechanical", "assertion": "true"}, "status": "pending"},
            {"lug_id": "lug-2", "verify": {"mode": "mechanical", "assertion": "true"}, "status": "pending"},
        ],
        "lifecycle_state": "active",
    }
    bolt = verify_engine.certify_pattern(pattern, spoke, session_id="sess-2", git_sha="ffff0000")
    assert bolt["certification_status"] == "certified"


def test_certify_failing_mechanical_is_partial(tmp_path):
    spoke = _make_spoke(tmp_path)
    pattern = {
        "id": "pattern-fail-v1",
        "version": "1.0.0",
        "items": [
            {"lug_id": "lug-1", "verify": {"mode": "mechanical", "assertion": "true"}, "status": "pending"},
            {"lug_id": "lug-2", "verify": {"mode": "mechanical", "assertion": "false"}, "status": "pending"},
        ],
        "lifecycle_state": "active",
    }
    bolt = verify_engine.certify_pattern(pattern, spoke, session_id="sess-3", git_sha="11112222")
    assert bolt["certification_status"] == "partial"
    by_lug = {i["lug_id"]: i for i in bolt["items"]}
    assert by_lug["lug-2"]["result"] == "fail"


def _write_pattern(spoke, pattern):
    """Write a pattern to active/ and return its path."""
    active = spoke / "WAI-Spoke" / "patterns" / "bytype" / "pattern" / "active"
    active.mkdir(parents=True, exist_ok=True)
    p = active / f"{pattern['id']}.json"
    p.write_text(json.dumps(pattern))
    return p


def test_certify_certified_transitions_pattern(tmp_path):
    """All-pass: pattern moves to certified/, fields updated, items verified."""
    spoke = _make_spoke(tmp_path)
    pattern = {
        "id": "pattern-all-pass-v2",
        "version": "1.0.0",
        "title": "All pass",
        "lifecycle_state": "active",
        "bolt_id": None,
        "certified_at": None,
        "items": [
            {"lug_id": "lug-1", "verify": {"mode": "mechanical", "assertion": "true"}, "status": "pending"},
            {"lug_id": "lug-2", "verify": {"mode": "mechanical", "assertion": "true"}, "status": "pending"},
        ],
    }
    p_path = _write_pattern(spoke, pattern)
    bolt = verify_engine.certify_pattern(
        pattern, spoke, session_id="sess-t", git_sha="aabb0011",
        pattern_path=p_path,
    )
    assert bolt["certification_status"] == "certified"

    cert_dir = spoke / "WAI-Spoke" / "patterns" / "bytype" / "pattern" / "certified"
    cert_file = cert_dir / "pattern-all-pass-v2.json"
    assert cert_file.exists(), "pattern not moved to certified/"
    assert not p_path.exists(), "original active/ file should be removed"

    updated = json.loads(cert_file.read_text())
    assert updated["lifecycle_state"] == "certified"
    assert updated["bolt_id"] == bolt["id"]
    assert updated["certified_at"] is not None
    assert all(i["status"] == "verified" for i in updated["items"])


def test_certify_partial_updates_bolt_id_stays_active(tmp_path):
    """Partial: pattern stays in active/ with bolt_id set, lifecycle unchanged."""
    spoke = _make_spoke(tmp_path)
    pattern = {
        "id": "pattern-partial-v1",
        "version": "1.0.0",
        "lifecycle_state": "active",
        "bolt_id": None,
        "items": [
            {"lug_id": "lug-1", "verify": {"mode": "mechanical", "assertion": "true"}, "status": "pending"},
            {"lug_id": "lug-2", "verify": {"mode": "mechanical", "assertion": "false"}, "status": "pending"},
        ],
    }
    p_path = _write_pattern(spoke, pattern)
    bolt = verify_engine.certify_pattern(
        pattern, spoke, session_id="sess-t", git_sha="aabb0022",
        pattern_path=p_path,
    )
    assert bolt["certification_status"] == "partial"
    assert p_path.exists(), "partial pattern should remain in active/"

    updated = json.loads(p_path.read_text())
    assert updated["lifecycle_state"] == "active"
    assert updated["bolt_id"] == bolt["id"]


def test_certify_certified_index_reflects_transition(tmp_path):
    """After certified transition, WAI-PatternIndex shows lifecycle_state=certified."""
    spoke = _make_spoke(tmp_path)
    pattern = {
        "id": "pattern-idx-cert-v1",
        "version": "1.0.0",
        "title": "Idx cert",
        "lifecycle_state": "active",
        "bolt_id": None,
        "items": [
            {"lug_id": "lug-1", "verify": {"mode": "mechanical", "assertion": "true"}, "status": "pending"},
        ],
    }
    p_path = _write_pattern(spoke, pattern)
    verify_engine.certify_pattern(
        pattern, spoke, session_id="sess-t", git_sha="ccdd0033",
        pattern_path=p_path,
    )
    verify_engine.generate_pattern_index(spoke)
    idx = spoke / "WAI-Spoke" / "WAI-PatternIndex.jsonl"
    rows = [json.loads(l) for l in idx.read_text().strip().splitlines()]
    assert len(rows) == 1
    assert rows[0]["lifecycle_state"] == "certified"


def test_generate_pattern_index(tmp_path):
    spoke = _make_spoke(tmp_path)
    wai = spoke / "WAI-Spoke"
    pdir = wai / "patterns" / "bytype" / "pattern" / "active"
    (pdir / "pattern-idx-v1.json").write_text(json.dumps({
        "id": "pattern-idx-v1", "version": "1.0.0", "title": "Idx",
        "initiative_id": "init-1", "lifecycle_state": "active",
        "items": [{"lug_id": "a", "verify": {"mode": "mechanical"}, "status": "pending"}],
    }))
    idx = verify_engine.generate_pattern_index(spoke)
    assert idx.exists()
    rows = [json.loads(l) for l in idx.read_text().strip().splitlines()]
    assert len(rows) == 1
    assert rows[0]["id"] == "pattern-idx-v1"
    assert rows[0]["item_count"] == 1
