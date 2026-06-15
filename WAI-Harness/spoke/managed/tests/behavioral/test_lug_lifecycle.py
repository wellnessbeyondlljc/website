"""
Behavioral tests for lug lifecycle operations.

Tests create/validate/move/close using real file operations on real bytype/ structure.
"""

import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.wai_validate import validate_lug, PEV_REQUIRED_TYPES


def _write_lug(path: Path, lug: dict):
    path.write_text(json.dumps(lug, indent=2))


def test_create_valid_lug(tmp_spoke):
    """A lug with all required fields validates cleanly."""
    lug = {
        "id": "task-test-001",
        "type": "task",
        "title": "Test task",
        "status": "open",
        "created_at": "2026-03-27T00:00:00Z",
        "created_by": "test",
        "routed_to": "LOCAL",
        "perceive": "Check that tests/behavioral/ exists and has conftest.py",
        "execute": "Run pytest tests/behavioral/ and verify all pass",
        "verify": "All tests pass with exit code 0, no skipped tests",
    }
    path = tmp_spoke / "WAI-Spoke/lugs/bytype/task/open/task-test-001.json"
    _write_lug(path, lug)

    violations = validate_lug(lug)
    assert violations == [], f"Valid lug should have no violations: {violations}"
    assert path.exists()


def test_task_without_pev_fails_validation(tmp_spoke):
    """A task lug without PEV fields fails validation."""
    lug = {
        "id": "task-no-pev",
        "type": "task",
        "title": "Task missing PEV",
        "status": "open",
        "created_at": "2026-03-27T00:00:00Z",
        "routed_to": "LOCAL",
    }
    violations = validate_lug(lug)
    pev_violations = [v for v in violations if "PEV" in v]
    assert len(pev_violations) == 3, f"Expected 3 PEV violations, got {pev_violations}"


def test_signal_does_not_require_pev(tmp_spoke):
    """Signal lugs do NOT require PEV fields."""
    lug = {
        "id": "signal-test",
        "type": "signal",
        "title": "Test signal",
        "status": "undelivered",
        "created_at": "2026-03-27T00:00:00Z",
        "routed_to": "SIGNAL",
        "_behavior_directive": {"action": "track_only"},
    }
    violations = validate_lug(lug)
    assert violations == [], f"Signal should validate without PEV: {violations}"


def test_invalid_type_caught(tmp_spoke):
    """A lug with an invalid type is caught."""
    lug = {
        "id": "bad-type",
        "type": "nonexistent_type",
        "title": "Bad type",
        "status": "open",
        "created_at": "2026-03-27T00:00:00Z",
    }
    violations = validate_lug(lug)
    assert any("not in canonical catalog" in v for v in violations)


def test_move_lug_open_to_completed(tmp_spoke):
    """Moving a lug from open/ to completed/ changes file location."""
    lug = {
        "id": "task-move-test",
        "type": "task",
        "title": "Task to complete",
        "status": "open",
        "created_at": "2026-03-27T00:00:00Z",
        "routed_to": "LOCAL",
        "perceive": "Check file exists in open/",
        "execute": "Move to completed/",
        "verify": "File is in completed/, not in open/",
    }

    open_path = tmp_spoke / "WAI-Spoke/lugs/bytype/task/open/task-move-test.json"
    completed_path = tmp_spoke / "WAI-Spoke/lugs/bytype/task/completed/task-move-test.json"

    _write_lug(open_path, lug)
    assert open_path.exists()

    # Simulate closeout: update status and move
    lug["status"] = "completed"
    _write_lug(completed_path, lug)
    open_path.unlink()

    assert not open_path.exists()
    assert completed_path.exists()
    moved_lug = json.loads(completed_path.read_text())
    assert moved_lug["status"] == "completed"


def test_scan_active_pattern(tmp_spoke):
    """The wai.md Step 4 scan pattern finds only active lugs."""
    wai = tmp_spoke / "WAI-Spoke"

    # Create active lugs
    active_lug = {"id": "active-1", "type": "task", "title": "Active", "status": "open",
                  "created_at": "2026-03-27T00:00:00Z", "routed_to": "LOCAL",
                  "perceive": "x" * 20, "execute": "x" * 20, "verify": "x" * 20}
    _write_lug(wai / "lugs/bytype/task/open/active-1.json", active_lug)

    # Create completed lug
    done_lug = {"id": "done-1", "type": "task", "title": "Done", "status": "completed",
                "created_at": "2026-03-27T00:00:00Z"}
    _write_lug(wai / "lugs/bytype/task/completed/done-1.json", done_lug)

    # Scan pattern from wai.md Step 4
    bytype = wai / "lugs" / "bytype"
    active_files = []
    for status_dir in ("open", "in_progress", "undelivered"):
        active_files.extend(bytype.rglob(f"*/{status_dir}/*.json"))

    assert len(active_files) == 1
    assert "active-1" in active_files[0].name


def test_all_pev_required_types():
    """Every PEV-required type should fail validation without PEV fields."""
    for lug_type in PEV_REQUIRED_TYPES:
        lug = {
            "id": f"test-{lug_type}",
            "type": lug_type,
            "title": f"Test {lug_type}",
            "status": "open",
            "created_at": "2026-03-27T00:00:00Z",
            "routed_to": "LOCAL",
        }
        violations = validate_lug(lug)
        pev_violations = [v for v in violations if "PEV" in v]
        assert len(pev_violations) == 3, f"Type '{lug_type}' should require all 3 PEV fields"
