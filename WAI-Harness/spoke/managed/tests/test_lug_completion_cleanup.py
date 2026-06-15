#!/usr/bin/env python3
"""Test that completed lugs are removed from their source status folders."""

import json
import tempfile
from pathlib import Path
import sys

# Add framework root to path
framework_root = Path(__file__).parent.parent
sys.path.insert(0, str(framework_root))
sys.path.insert(0, str(framework_root / "tools"))

from wai_ozi_config import OziConfig
from wai_ozi_dispatch import OziDispatch


def test_lug_cleanup_on_completion():
    """Verify that when a lug is promoted to completed/, the source file is deleted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a mock spoke structure
        spoke_wai = tmpdir / "WAI-Spoke"
        bytype = spoke_wai / "lugs" / "bytype"
        task_in_progress = bytype / "task" / "in_progress"
        task_completed = bytype / "task" / "completed"

        task_in_progress.mkdir(parents=True, exist_ok=True)
        task_completed.mkdir(parents=True, exist_ok=True)

        # Create a test lug in in_progress/
        lug_id = "test-task-001"
        lug_data = {
            "id": lug_id,
            "type": "task",
            "status": "in_progress",
            "title": "Test task",
            "description": "A test task for cleanup verification",
        }
        lug_path = task_in_progress / f"{lug_id}.json"
        lug_path.write_text(json.dumps(lug_data, indent=2) + "\n")

        # Verify the lug exists in in_progress
        assert lug_path.exists(), "Lug should exist in in_progress/"

        # Create OziConfig with temp spoke path
        config = OziConfig(spoke_path=str(spoke_wai))
        dispatch = OziDispatch(config)

        # Promote lug to completed
        workflow_data = {
            "completed_at": "2026-06-05T12:00:00",
            "dispatch_method": "test",
        }
        result = dispatch.update_lug_status(lug_id, "completed", workflow_data)

        # Verify the update succeeded
        assert result, "update_lug_status should return True"

        # Verify the lug now exists in completed/
        completed_lug_path = task_completed / f"{lug_id}.json"
        assert completed_lug_path.exists(), "Lug should exist in completed/"

        # Verify the source file is deleted from in_progress/
        assert not lug_path.exists(), f"Source lug should be deleted from in_progress/, but exists at {lug_path}"

        # Verify exactly one copy exists (find returns exactly one path)
        found_paths = list(bytype.rglob(f"{lug_id}.json"))
        assert len(found_paths) == 1, f"Expected exactly 1 copy of {lug_id}, found {len(found_paths)}: {found_paths}"
        assert found_paths[0] == completed_lug_path, "The single copy should be in completed/"

        # Verify the completed lug has correct status
        completed_lug = json.loads(completed_lug_path.read_text())
        assert completed_lug["status"] == "completed", "Completed lug should have status=completed"
        assert completed_lug["workflow"]["completed_at"] == "2026-06-05T12:00:00"

        print("✓ Test passed: Lug cleanup on completion works correctly")


def test_lug_cleanup_all_types():
    """Verify cleanup works for all dispatchable lug types."""
    lug_types = ["task", "bug", "feature", "implementation"]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        spoke_wai = tmpdir / "WAI-Spoke"
        bytype = spoke_wai / "lugs" / "bytype"

        config = OziConfig(spoke_path=str(spoke_wai))
        dispatch = OziDispatch(config)

        for lug_type in lug_types:
            # Create structure for this type
            type_open = bytype / lug_type / "open"
            type_completed = bytype / lug_type / "completed"
            type_open.mkdir(parents=True, exist_ok=True)
            type_completed.mkdir(parents=True, exist_ok=True)

            # Create test lug
            lug_id = f"test-{lug_type}-cleanup"
            lug_data = {
                "id": lug_id,
                "type": lug_type,
                "status": "open",
                "title": f"Test {lug_type}",
            }
            lug_path = type_open / f"{lug_id}.json"
            lug_path.write_text(json.dumps(lug_data, indent=2) + "\n")

            # Promote to completed
            result = dispatch.update_lug_status(lug_id, "completed", {"dispatch_method": "test"})
            assert result, f"Failed to promote {lug_type} to completed"

            # Verify cleanup
            assert not lug_path.exists(), f"Source {lug_type} should be deleted from open/"
            completed_path = type_completed / f"{lug_id}.json"
            assert completed_path.exists(), f"{lug_type} should exist in completed/"

            # Verify only one copy
            found = list(bytype.rglob(f"{lug_id}.json"))
            assert len(found) == 1, f"Expected 1 copy of {lug_type} test lug, found {len(found)}"

        print(f"✓ Test passed: Cleanup works for all lug types: {', '.join(lug_types)}")


if __name__ == "__main__":
    test_lug_cleanup_on_completion()
    test_lug_cleanup_all_types()
    print("\n✓ All lug cleanup tests passed!")
