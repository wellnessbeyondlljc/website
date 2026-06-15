"""Tests for ceremony + adoption bolt emission in verify_engine.

Covers: certified vs partial aggregation, skipped-step exclusion, schema
validity of emitted bolts, and idempotent overwrite per (session, type).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import verify_engine as ve  # noqa: E402

BOLT_SCHEMA = json.loads((REPO / "schemas" / "bolt.schema.json").read_text())
REQUIRED = BOLT_SCHEMA["required"]
ITEM_RESULT_ENUM = {"pass", "fail", "pending"}
KIND_ENUM = set(BOLT_SCHEMA["properties"]["kind"]["enum"])


def _assert_schema_valid(bolt):
    for field in REQUIRED:
        assert field in bolt, f"missing required field {field}"
    assert bolt["kind"] in KIND_ENUM
    assert bolt["certification_status"] in {"certified", "partial"}
    for item in bolt["items"]:
        assert item["result"] in ITEM_RESULT_ENUM
        assert "lug_id" in item and "mode" in item


@pytest.fixture
def spoke(tmp_path):
    (tmp_path / "WAI-Spoke").mkdir()
    return tmp_path


def test_ceremony_all_pass_certified(spoke):
    steps = [
        {"step_id": "step-0-test-gate", "result": "pass", "note": "exit=0"},
        {"step_id": "step-11-staging", "result": "pass"},
    ]
    bolt = ve.emit_ceremony_bolt("session-T", "closeout", "standard", steps, spoke, git_sha="abc1234")
    assert bolt["certification_status"] == "certified"
    assert bolt["kind"] == "ceremony"
    assert bolt["pattern_id"] is None
    _assert_schema_valid(bolt)
    assert Path(bolt["_bolt_path"]).exists()


def test_ceremony_pending_is_partial(spoke):
    steps = [
        {"step_id": "step-a", "result": "pass"},
        {"step_id": "step-b", "mode": "attested", "result": "pending"},
    ]
    bolt = ve.emit_ceremony_bolt("session-T", "closeout", "standard", steps, spoke)
    assert bolt["certification_status"] == "partial"
    _assert_schema_valid(bolt)


def test_ceremony_skipped_steps_excluded_from_tally(spoke):
    # A conversation-only closeout: one step ran (pass), the rest skipped.
    steps = [
        {"step_id": "step-6-terminal", "result": "pass"},
        {"step_id": "step-9b-teachings", "result": "pending", "skipped": True},
        {"step_id": "step-5d-changelog", "result": "pending", "skipped": True},
    ]
    bolt = ve.emit_ceremony_bolt("session-T", "closeout", "minimal", steps, spoke)
    assert bolt["certification_status"] == "certified"  # every executed step passed
    skipped = [i for i in bolt["items"] if i["skipped"]]
    assert len(skipped) == 2
    _assert_schema_valid(bolt)


def test_ceremony_fail_is_partial(spoke):
    steps = [{"step_id": "step-0-test-gate", "result": "fail", "note": "pytest exit=1"}]
    bolt = ve.emit_ceremony_bolt("session-T", "closeout", "standard", steps, spoke)
    assert bolt["certification_status"] == "partial"
    _assert_schema_valid(bolt)


def test_ceremony_idempotent_overwrite(spoke):
    a = ve.emit_ceremony_bolt("session-T", "closeout", "standard",
                              [{"step_id": "s1", "result": "pass"}], spoke)
    b = ve.emit_ceremony_bolt("session-T", "closeout", "standard",
                              [{"step_id": "s1", "result": "pass"}, {"step_id": "s2", "result": "pass"}], spoke)
    assert a["id"] == b["id"]
    on_disk = json.loads(Path(b["_bolt_path"]).read_text())
    assert len(on_disk["items"]) == 2  # overwritten, not duplicated
    ceremony_dir = spoke / "WAI-Spoke" / "bolts" / "bytype" / "ceremony" / "recorded"
    assert len(list(ceremony_dir.glob("*.json"))) == 1


def test_adoption_bolt(spoke):
    checks = [
        {"component": "WAI-Spoke/WAI-State.json", "result": "pass"},
        {"component": ".claude/hooks", "result": "pass"},
    ]
    bolt = ve.emit_adoption_bolt("session-T", "3.0.0", checks, spoke, git_sha="def5678")
    assert bolt["kind"] == "adoption"
    assert bolt["id"] == "bolt-session-T-adoption-base-3.0.0"
    assert bolt["certification_status"] == "certified"
    _assert_schema_valid(bolt)
    assert (spoke / "WAI-Spoke" / "bolts" / "bytype" / "adoption" / "recorded").exists()


def test_bolt_index_includes_meta_kinds(spoke):
    ve.emit_ceremony_bolt("session-T", "closeout", "standard", [{"step_id": "s1", "result": "pass"}], spoke)
    ve.emit_adoption_bolt("session-T", "3.0.0", [{"component": "c1", "result": "pass"}], spoke)
    idx = ve.generate_bolt_index(spoke)
    rows = [json.loads(l) for l in idx.read_text().splitlines() if l.strip()]
    kinds = {r["kind"] for r in rows}
    assert "ceremony" in kinds and "adoption" in kinds


def test_cli_emit_ceremony(spoke):
    out = subprocess.run(
        [sys.executable, str(REPO / "tools" / "verify_engine.py"), "emit-ceremony",
         "--session-id", "session-CLI", "--ceremony-type", "closeout",
         "--steps", json.dumps([{"step_id": "s1", "result": "pass"}]),
         "--spoke-path", str(spoke), "--git-sha", "cli12345"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["certification_status"] == "certified"
    assert Path(payload["path"]).exists()
