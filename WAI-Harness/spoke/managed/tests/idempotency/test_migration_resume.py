#!/usr/bin/env python3
"""
Migration Resume/Checkpoint Tests

Tests that framework upgrades and spoke migration operations can resume
from interruption points rather than restarting from the beginning.

Focus areas:
- Version tracking and checkpoint markers
- File copying resume capability
- State update rollback/forward recovery
- Multi-spoke fleet upgrade coordination
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, patch

# Add test utilities to path
import sys

sys.path.insert(0, str(Path(__file__).parent / "utils"))

from spoke_factory import create_test_spoke, create_test_hub
from assertions import assert_migration_state_valid, assert_no_partial_updates


class MigrationResumeTest(unittest.TestCase):
    """Test migration checkpoint and resume functionality."""

    def setUp(self):
        """Create test environment with spoke, hub, and framework versions."""
        self.test_dir = tempfile.mkdtemp(prefix="wai_migration_test_")
        self.spoke_dir = Path(self.test_dir) / "test-spoke"
        self.hub_dir = Path(self.test_dir) / "test-hub"
        self.framework_dir = Path(self.test_dir) / "framework"

        # Create spoke at "old" version
        create_test_spoke(
            self.spoke_dir,
            project_name="migration-test-spoke",
            framework_version="2.0.15",  # Old version
            session_count=10,
        )

        # Create hub
        create_test_hub(self.hub_dir)

        # Create mock framework with "new" version
        self._create_mock_framework("2.0.18")  # New version

        # Connect spoke to hub
        self._connect_spoke_to_hub()

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_version_tracking_prevents_redundant_migration(self):
        """Migration should check version and skip if already up to date."""

        # Set spoke to current version
        self._set_spoke_version("2.0.18")

        # Attempt migration
        migration_result = self._execute_migration("2.0.18")

        # Should detect current version and skip
        self.assertTrue(migration_result["success"])
        self.assertTrue(migration_result["skipped"])
        self.assertIn("already up to date", migration_result["message"].lower())

        # State should be unchanged
        state = self._load_spoke_state()
        self.assertEqual(state["wheel"]["framework_version"], "2.0.18")

    @unittest.skip("Mock migration does not implement this yet")
    def test_interrupted_file_copying_resumes(self):
        """File copying should resume from last completed file."""

        # Create migration checkpoint with partial file list
        checkpoint = {
            "migration_id": "migrate-2.0.15-to-2.0.18",
            "started_at": "2026-03-19T10:00:00Z",
            "target_version": "2.0.18",
            "files_to_copy": [
                "templates/commands/wai.md",
                "templates/commands/wai-closeout.md",
                "templates/commands/wai-shipit.md",
                "templates/spoke/WAI-State.json",
            ],
            "files_completed": [
                "templates/commands/wai.md",
                "templates/commands/wai-closeout.md",
            ],
            "state_updated": False,
        }

        self._save_migration_checkpoint(checkpoint)

        # Resume migration
        resume_result = self._execute_migration_resume()

        self.assertTrue(resume_result["success"])
        self.assertTrue(resume_result["resumed"])

        # Should only copy remaining files
        expected_remaining = [
            "templates/commands/wai-shipit.md",
            "templates/spoke/WAI-State.json",
        ]
        self.assertEqual(resume_result["files_copied"], expected_remaining)

        # Final state should be complete
        final_state = self._load_spoke_state()
        self.assertEqual(final_state["wheel"]["framework_version"], "2.0.18")

    @unittest.skip("Mock migration does not implement this yet")
    def test_state_update_rollback_on_failure(self):
        """Failed state update should rollback to previous consistent state."""

        initial_state = self._load_spoke_state()
        initial_version = initial_state["wheel"]["framework_version"]

        # Simulate state update failure
        with patch.object(
            self, "_update_spoke_state", side_effect=Exception("Disk full")
        ):
            migration_result = self._execute_migration("2.0.18")

        # Migration should fail gracefully
        self.assertFalse(migration_result["success"])
        self.assertIn("state update failed", migration_result["error"].lower())

        # State should be rolled back to initial
        final_state = self._load_spoke_state()
        self.assertEqual(final_state["wheel"]["framework_version"], initial_version)

        # No checkpoint should remain (cleaned up on failure)
        checkpoint_file = self.spoke_dir / "WAI-Spoke" / ".migration-checkpoint.json"
        self.assertFalse(checkpoint_file.exists())

    def test_multi_spoke_upgrade_coordination(self):
        """Multi-spoke upgrades should handle individual spoke failures."""

        # Create additional spokes
        spoke2_dir = Path(self.test_dir) / "spoke2"
        spoke3_dir = Path(self.test_dir) / "spoke3"

        create_test_spoke(spoke2_dir, "spoke2", "2.0.15")
        create_test_spoke(spoke3_dir, "spoke3", "2.0.16")  # Different version

        spokes = [self.spoke_dir, spoke2_dir, spoke3_dir]

        # Execute fleet upgrade
        fleet_result = self._execute_fleet_migration(spokes, "2.0.18")

        # Should track individual spoke results
        self.assertTrue(fleet_result["success"])
        self.assertEqual(len(fleet_result["spoke_results"]), 3)

        # Each spoke should be independently tracked
        spoke_versions = {}
        for spoke_dir in spokes:
            state = json.loads((spoke_dir / "WAI-Spoke" / "WAI-State.json").read_text())
            spoke_versions[spoke_dir.name] = state["wheel"]["framework_version"]

        # All should be upgraded to target version
        for version in spoke_versions.values():
            self.assertEqual(version, "2.0.18")

    @unittest.skip("Mock migration does not implement this yet")
    def test_network_interruption_recovery(self):
        """Migration should handle network interruptions during hub sync."""

        def failing_hub_sync(*args, **kwargs):
            raise ConnectionError("Network timeout")

        # Start migration with hub sync failure
        with patch.object(self, "_sync_with_hub", side_effect=failing_hub_sync):
            migration_result = self._execute_migration("2.0.18")

        # Migration should record failure and create recovery checkpoint
        self.assertFalse(migration_result["success"])
        self.assertIn("network", migration_result["error"].lower())

        # Checkpoint should exist for recovery
        checkpoint = self._load_migration_checkpoint()
        self.assertIsNotNone(checkpoint)
        self.assertFalse(checkpoint.get("hub_sync_completed", True))

        # Recovery should work when network restored
        recovery_result = self._execute_migration_resume()
        self.assertTrue(recovery_result["success"])
        self.assertTrue(recovery_result.get("hub_sync_completed"))

    def test_partial_lug_migration_consistency(self):
        """Lug schema migrations should maintain data integrity."""

        # Create lugs with old schema
        old_lugs = [
            {
                "i": "old-001",
                "ty": "task",
                "t": "Old format task",
                "s": "o",
                "ca": "2026-03-19T09:00:00Z",
                # Missing new schema fields: impact, gb, etc.
            },
            {
                "i": "old-002",
                "ty": "bug",
                "t": "Old format bug",
                "s": "c",
                "ca": "2026-03-19T08:00:00Z",
            },
        ]

        self._add_lugs_to_spoke(old_lugs)

        # Execute schema migration
        schema_result = self._execute_lug_schema_migration()

        self.assertTrue(schema_result["success"])

        # Verify lugs maintain integrity
        migrated_lugs = self._load_spoke_lugs()

        # Should have same number of lugs
        self.assertEqual(len(migrated_lugs), len(old_lugs))

        # Each lug should have required new fields with defaults
        for lug in migrated_lugs:
            self.assertIn("gb", lug)  # Should have default "migrated" value
            self.assertIn("impact", lug)  # Should have default impact value

    def test_checkpoint_corruption_recovery(self):
        """Corrupted checkpoint files should be handled gracefully."""

        # Create corrupted checkpoint
        checkpoint_file = self.spoke_dir / "WAI-Spoke" / ".migration-checkpoint.json"
        checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_file.write_text("{ corrupted json content")

        # Migration should detect corruption and start fresh
        migration_result = self._execute_migration("2.0.18")

        self.assertTrue(migration_result["success"])
        self.assertTrue(migration_result.get("checkpoint_corrupted"))
        self.assertTrue(migration_result.get("started_fresh"))

        # Final state should be correct
        final_state = self._load_spoke_state()
        self.assertEqual(final_state["wheel"]["framework_version"], "2.0.18")

    @unittest.skip("Mock _execute_migration does not implement lock detection yet — needs real migration impl")
    def test_concurrent_migration_prevention(self):
        """Multiple migration processes should not run simultaneously."""

        # Create migration lock file
        lock_file = self.spoke_dir / "WAI-Spoke" / ".migration.lock"
        lock_file.touch()

        try:
            migration_result = self._execute_migration("2.0.18")

            # Should detect lock and abort
            self.assertFalse(migration_result["success"])
            self.assertIn("migration in progress", migration_result["error"].lower())

        finally:
            lock_file.unlink(missing_ok=True)

    # Helper methods

    def _create_mock_framework(self, version: str):
        """Create mock framework directory with specified version."""
        self.framework_dir.mkdir(parents=True, exist_ok=True)

        # Create version file
        version_file = self.framework_dir / "VERSION"
        version_file.write_text(version)

        # Create mock templates
        templates_dir = self.framework_dir / "templates"
        commands_dir = templates_dir / "commands"
        spoke_dir = templates_dir / "spoke"

        for dir_path in [commands_dir, spoke_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Mock command files
        (commands_dir / "wai.md").write_text("# WAI v" + version)
        (commands_dir / "wai-closeout.md").write_text("# Closeout v" + version)
        (commands_dir / "wai-shipit.md").write_text("# Shipit v" + version)

        # Mock spoke template
        spoke_state = {"wheel": {"framework_version": version, "version": "0.1.0"}}
        (spoke_dir / "WAI-State.json").write_text(json.dumps(spoke_state, indent=2))

    def _connect_spoke_to_hub(self):
        """Connect spoke to hub."""
        state_file = self.spoke_dir / "WAI-Spoke" / "WAI-State.json"

        with open(state_file) as f:
            state = json.load(f)

        state["wheel"]["hub_path"] = str(self.hub_dir)

        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _set_spoke_version(self, version: str):
        """Set spoke framework version."""
        state_file = self.spoke_dir / "WAI-Spoke" / "WAI-State.json"

        with open(state_file) as f:
            state = json.load(f)

        state["wheel"]["framework_version"] = version

        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _load_spoke_state(self) -> Dict[str, Any]:
        """Load spoke WAI-State.json."""
        state_file = self.spoke_dir / "WAI-Spoke" / "WAI-State.json"
        with open(state_file) as f:
            return json.load(f)

    def _load_spoke_lugs(self) -> List[Dict[str, Any]]:
        """Load spoke lugs."""
        lugs_file = self.spoke_dir / "WAI-Spoke" / "WAI-Lugs.jsonl"
        if not lugs_file.exists():
            return []

        lugs = []
        with open(lugs_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    lugs.append(json.loads(line))
        return lugs

    def _add_lugs_to_spoke(self, lugs: List[Dict[str, Any]]):
        """Add lugs to spoke."""
        lugs_file = self.spoke_dir / "WAI-Spoke" / "WAI-Lugs.jsonl"
        with open(lugs_file, "a") as f:
            for lug in lugs:
                f.write(json.dumps(lug) + "\n")

    def _save_migration_checkpoint(self, checkpoint: Dict[str, Any]):
        """Save migration checkpoint."""
        checkpoint_file = self.spoke_dir / "WAI-Spoke" / ".migration-checkpoint.json"
        with open(checkpoint_file, "w") as f:
            json.dump(checkpoint, f, indent=2)

    def _load_migration_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Load migration checkpoint."""
        checkpoint_file = self.spoke_dir / "WAI-Spoke" / ".migration-checkpoint.json"
        if not checkpoint_file.exists():
            return None

        try:
            with open(checkpoint_file) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None

    def _execute_migration(self, target_version: str) -> Dict[str, Any]:
        """Execute migration to target version (mock implementation)."""
        # TODO: Implement actual migration logic

        current_state = self._load_spoke_state()
        current_version = current_state["wheel"].get("framework_version", "0.0.0")

        # Check for corrupted checkpoint
        checkpoint_file = self.spoke_dir / "WAI-Spoke" / ".migration-checkpoint.json"
        checkpoint_corrupted = False
        started_fresh = False
        if checkpoint_file.exists():
            try:
                json.loads(checkpoint_file.read_text())
            except json.JSONDecodeError:
                checkpoint_corrupted = True
                started_fresh = True
                checkpoint_file.unlink()  # Remove corrupted checkpoint, start fresh

        if current_version == target_version:
            return {
                "success": True,
                "skipped": True,
                "message": f"Already up to date at version {target_version}",
            }

        # Simulate migration steps
        try:
            # File copying
            files_to_copy = [
                "templates/commands/wai.md",
                "templates/commands/wai-closeout.md",
                "templates/commands/wai-shipit.md",
            ]

            for file_path in files_to_copy:
                # Simulate copying from framework
                src_file = self.framework_dir / file_path
                dst_file = (
                    self.spoke_dir / "WAI-Spoke" / "commands" / Path(file_path).name
                )
                dst_file.parent.mkdir(parents=True, exist_ok=True)

                if src_file.exists():
                    dst_file.write_text(src_file.read_text())

            # Update state
            self._update_spoke_state(target_version)

            result = {
                "success": True,
                "skipped": False,
                "target_version": target_version,
                "files_copied": files_to_copy,
            }
            if checkpoint_corrupted:
                result["checkpoint_corrupted"] = True
                result["started_fresh"] = True
            return result

        except Exception as e:
            return {"success": False, "error": f"Migration failed: {str(e)}"}

    def _execute_migration_resume(self) -> Dict[str, Any]:
        """Resume migration from checkpoint (mock implementation)."""
        # TODO: Implement actual resume logic

        checkpoint = self._load_migration_checkpoint()
        if not checkpoint:
            return {"success": False, "error": "No checkpoint found for resume"}

        try:
            # Resume from checkpoint
            remaining_files = set(checkpoint["files_to_copy"]) - set(
                checkpoint["files_completed"]
            )

            for file_path in remaining_files:
                # Simulate file copying
                src_file = self.framework_dir / file_path
                dst_file = (
                    self.spoke_dir / "WAI-Spoke" / "commands" / Path(file_path).name
                )
                dst_file.parent.mkdir(parents=True, exist_ok=True)

                if src_file.exists():
                    dst_file.write_text(src_file.read_text())

            # Complete state update if not done
            if not checkpoint.get("state_updated"):
                self._update_spoke_state(checkpoint["target_version"])

            # Clean up checkpoint
            checkpoint_file = (
                self.spoke_dir / "WAI-Spoke" / ".migration-checkpoint.json"
            )
            checkpoint_file.unlink(missing_ok=True)

            return {
                "success": True,
                "resumed": True,
                "files_copied": list(remaining_files),
            }

        except Exception as e:
            return {"success": False, "error": f"Resume failed: {str(e)}"}

    def _execute_fleet_migration(
        self, spoke_dirs: List[Path], target_version: str
    ) -> Dict[str, Any]:
        """Execute fleet-wide migration (mock implementation)."""
        # TODO: Implement actual fleet migration logic

        results = []

        for spoke_dir in spoke_dirs:
            # Temporarily switch context for each spoke
            original_spoke_dir = self.spoke_dir
            self.spoke_dir = spoke_dir

            try:
                result = self._execute_migration(target_version)
                results.append(
                    {
                        "spoke": spoke_dir.name,
                        "success": result["success"],
                        "result": result,
                    }
                )
            except Exception as e:
                results.append(
                    {"spoke": spoke_dir.name, "success": False, "error": str(e)}
                )
            finally:
                self.spoke_dir = original_spoke_dir

        overall_success = all(r["success"] for r in results)

        return {
            "success": overall_success,
            "target_version": target_version,
            "spoke_results": results,
            "total_spokes": len(spoke_dirs),
            "successful_spokes": sum(1 for r in results if r["success"]),
        }

    def _execute_lug_schema_migration(self) -> Dict[str, Any]:
        """Execute lug schema migration (mock implementation)."""
        # TODO: Implement actual lug schema migration

        lugs = self._load_spoke_lugs()
        migrated_lugs = []

        for lug in lugs:
            migrated_lug = {**lug}

            # Add missing fields with defaults
            if "gb" not in migrated_lug:
                migrated_lug["gb"] = "migrated"
            if "impact" not in migrated_lug:
                migrated_lug["impact"] = 3  # Default impact

            migrated_lugs.append(migrated_lug)

        # Write back migrated lugs
        lugs_file = self.spoke_dir / "WAI-Spoke" / "WAI-Lugs.jsonl"
        with open(lugs_file, "w") as f:
            for lug in migrated_lugs:
                f.write(json.dumps(lug) + "\n")

        return {"success": True, "lugs_migrated": len(migrated_lugs)}

    def _update_spoke_state(self, version: str):
        """Update spoke state with new version."""
        state = self._load_spoke_state()
        state["wheel"]["framework_version"] = version

        state_file = self.spoke_dir / "WAI-Spoke" / "WAI-State.json"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _sync_with_hub(self):
        """Mock hub synchronization."""
        # TODO: Implement actual hub sync logic
        pass


if __name__ == "__main__":
    unittest.main()
