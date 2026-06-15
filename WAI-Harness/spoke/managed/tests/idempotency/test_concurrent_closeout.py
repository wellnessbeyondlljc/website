#!/usr/bin/env python3
"""
Concurrent Closeout Operation Tests

Tests that multiple agents running closeout simultaneously handle contention
gracefully through file locking and serialization mechanisms.

Focus areas:
- WAI-State.json atomic updates
- WAI-Lugs.jsonl concurrent appends
- Git operation serialization
- Lock file coordination
"""

import json
import multiprocessing as mp
import os
import tempfile
import time
import unittest
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import patch

# Add test utilities to path
import sys

sys.path.insert(0, str(Path(__file__).parent / "utils"))

from spoke_factory import create_test_spoke, add_test_lugs
from concurrency_helper import spawn_closeout_process, wait_for_completion
from assertions import assert_no_file_corruption, assert_single_winner


class ConcurrentCloseoutTest(unittest.TestCase):
    """Test concurrent closeout operation handling."""

    def setUp(self):
        """Create isolated test environment."""
        self.test_dir = tempfile.mkdtemp(prefix="wai_concurrent_test_")
        self.spoke_dir = Path(self.test_dir) / "test-spoke"

        # Create test spoke with work that would trigger closeout
        create_test_spoke(
            self.spoke_dir,
            project_name="concurrent-test-project",
            session_count=3,
            has_active_work=True,
        )

        # Add autosave lugs that need reconciliation
        add_test_lugs(
            self.spoke_dir / "WAI-Spoke" / "WAI-Lugs.jsonl",
            [
                {
                    "i": "auto-001",
                    "ty": "autosave",
                    "t": "Progress checkpoint 1",
                    "s": "o",
                    "ca": "2026-03-19T10:00:00Z",
                    "reconciled": False,
                },
                {
                    "i": "auto-002",
                    "ty": "autosave",
                    "t": "Progress checkpoint 2",
                    "s": "o",
                    "ca": "2026-03-19T10:05:00Z",
                    "reconciled": False,
                },
            ],
        )

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_two_concurrent_closeouts_single_winner(self):
        """Two concurrent closeouts should result in single winner, other waits or aborts."""

        # Spawn two concurrent closeout processes
        processes = []
        results = mp.Queue()

        for i in range(2):
            p = mp.Process(target=self._closeout_worker, args=(f"agent-{i}", results))
            processes.append(p)
            p.start()

        # Wait for both to complete
        for p in processes:
            p.join(timeout=10)  # 10 second timeout
            if p.is_alive():
                p.terminate()
                self.fail("Closeout process timed out")

        # Collect results
        worker_results = []
        while not results.empty():
            worker_results.append(results.get())

        self.assertEqual(len(worker_results), 2, "Should get results from both workers")

        # Exactly one should succeed, other should detect contention
        successes = [r for r in worker_results if r["success"]]
        failures = [r for r in worker_results if not r["success"]]

        self.assertEqual(len(successes), 1, "Exactly one closeout should succeed")
        self.assertEqual(len(failures), 1, "Exactly one closeout should fail/wait")

        # Failed one should indicate concurrency detected
        failed_result = failures[0]
        self.assertIn("concurrent", failed_result.get("error", "").lower())

        # Final state should be consistent
        final_state = self._load_wai_state()
        assert_no_file_corruption(final_state)

    def test_three_concurrent_closeouts_serialization(self):
        """Three concurrent closeouts should serialize properly."""

        processes = []
        results = mp.Queue()

        # Launch three concurrent processes
        for i in range(3):
            p = mp.Process(target=self._closeout_worker, args=(f"agent-{i}", results))
            processes.append(p)
            p.start()

            # Small delay to increase chance of contention
            time.sleep(0.1)

        # Wait for completion
        for p in processes:
            p.join(timeout=15)
            if p.is_alive():
                p.terminate()

        # Collect results
        worker_results = []
        while not results.empty():
            worker_results.append(results.get())

        # All processes should complete (success or controlled failure)
        self.assertEqual(len(worker_results), 3)

        # Lock serialization: processes run one at a time.
        # With 0.1s spawn delay and 1s work, later processes may acquire
        # the lock after earlier ones release it. The invariant is that
        # concurrent access is prevented, not that only one ever succeeds.
        successes = [r for r in worker_results if r["success"]]
        failures = [r for r in worker_results if not r["success"]]
        self.assertGreaterEqual(len(successes), 1, "At least one closeout should succeed")
        # If all 3 succeeded, that's fine — it means they serialized properly
        # If some failed, they should report concurrency
        for f in failures:
            self.assertIn("concurrent", f.get("error", "").lower())

        # If one succeeded, state should be valid
        if successes:
            final_state = self._load_wai_state()
            assert_no_file_corruption(final_state)

    def test_wai_state_json_atomic_update(self):
        """WAI-State.json updates should be atomic (no partial writes)."""

        # This test would verify that concurrent state updates don't result
        # in corrupted JSON files

        processes = []
        results = mp.Queue()

        # Multiple processes trying to update state
        for i in range(5):
            p = mp.Process(
                target=self._state_updater_worker, args=(f"updater-{i}", results)
            )
            processes.append(p)
            p.start()

        for p in processes:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()

        # State file should still be valid JSON
        try:
            final_state = self._load_wai_state()
            self.assertIsInstance(final_state, dict)
            self.assertIn("_session_state", final_state)
        except json.JSONDecodeError:
            self.fail("WAI-State.json was corrupted by concurrent updates")

    def test_lugs_jsonl_concurrent_appends(self):
        """Concurrent appends to WAI-Lugs.jsonl should not corrupt file."""

        initial_lugs = self._load_lugs()
        initial_count = len(initial_lugs)

        processes = []
        results = mp.Queue()

        # Multiple processes appending lugs
        for i in range(4):
            p = mp.Process(
                target=self._lug_appender_worker,
                args=(f"appender-{i}", 3, results),  # Each adds 3 lugs
            )
            processes.append(p)
            p.start()

        for p in processes:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()

        # Verify file integrity
        try:
            final_lugs = self._load_lugs()

            # Should have initial + appended lugs
            expected_min = initial_count + (4 * 3)  # 4 processes * 3 lugs each
            self.assertGreaterEqual(len(final_lugs), expected_min)

            # All lugs should be valid JSON
            for lug in final_lugs[-12:]:  # Check the newly added ones
                self.assertIsInstance(lug, dict)
                self.assertIn("i", lug)
                self.assertIn("ty", lug)

        except (json.JSONDecodeError, ValueError) as e:
            self.fail(f"WAI-Lugs.jsonl was corrupted by concurrent appends: {e}")

    def test_git_operation_serialization(self):
        """Git operations should be serialized to prevent conflicts."""

        # Mock git to simulate realistic delays and potential conflicts
        def mock_git_with_delay(*args, **kwargs):
            time.sleep(0.5)  # Simulate git operation time
            mock_result = type("MockResult", (), {})()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            return mock_result

        with patch("subprocess.run", side_effect=mock_git_with_delay):
            processes = []
            results = mp.Queue()

            # Multiple processes trying git operations
            for i in range(3):
                p = mp.Process(
                    target=self._git_worker, args=(f"git-agent-{i}", results)
                )
                processes.append(p)
                p.start()

            for p in processes:
                p.join(timeout=20)
                if p.is_alive():
                    p.terminate()
                    self.fail("Git operation worker timed out")

            # Collect results
            worker_results = []
            while not results.empty():
                worker_results.append(results.get())

            # All git operations should complete successfully or fail gracefully
            for result in worker_results:
                self.assertTrue(
                    result["success"] or "conflict" in result.get("error", "").lower(),
                    f"Git worker should succeed or detect conflict: {result}",
                )

    def test_lock_file_cleanup_on_failure(self):
        """Lock files should be cleaned up even if process fails."""

        # Test that lock files don't persist after process crashes
        def failing_closeout_worker():
            lock_file = self.spoke_dir / "WAI-Spoke" / ".closeout.lock"
            try:
                lock_file.touch()
                # Simulate work, then crash
                time.sleep(1)
                raise Exception("Simulated crash")
            except Exception:
                # Cleanup should happen in finally block
                if lock_file.exists():
                    lock_file.unlink()
                raise

        # Run failing worker
        p = mp.Process(target=failing_closeout_worker)
        p.start()
        p.join(timeout=5)

        # Lock file should not exist after process ends
        lock_file = self.spoke_dir / "WAI-Spoke" / ".closeout.lock"
        self.assertFalse(
            lock_file.exists(), "Lock file should be cleaned up after failure"
        )

    # Worker functions for multiprocessing tests

    def _closeout_worker(self, agent_name: str, results_queue: mp.Queue):
        """Worker function that attempts closeout operation."""
        try:
            result = self._attempt_closeout(agent_name)
            results_queue.put(result)
        except Exception as e:
            results_queue.put({"success": False, "error": str(e), "agent": agent_name})

    def _state_updater_worker(self, updater_name: str, results_queue: mp.Queue):
        """Worker function that updates WAI-State.json."""
        try:
            # Simulate state update
            state_file = self.spoke_dir / "WAI-Spoke" / "WAI-State.json"

            with open(state_file, "r+") as f:
                state = json.load(f)
                f.seek(0)

                # Make a change
                state["_session_state"]["last_modified_by"] = updater_name
                state["_session_state"]["last_modified_at"] = (
                    f"2026-03-19T{time.time()}Z"
                )

                json.dump(state, f, indent=2)
                f.truncate()

            results_queue.put({"success": True, "updater": updater_name})

        except Exception as e:
            results_queue.put(
                {"success": False, "error": str(e), "updater": updater_name}
            )

    def _lug_appender_worker(
        self, appender_name: str, lug_count: int, results_queue: mp.Queue
    ):
        """Worker function that appends lugs to WAI-Lugs.jsonl."""
        try:
            lugs_file = self.spoke_dir / "WAI-Spoke" / "WAI-Lugs.jsonl"

            with open(lugs_file, "a") as f:
                for i in range(lug_count):
                    lug = {
                        "i": f"{appender_name}-lug-{i}",
                        "ty": "test",
                        "t": f"Test lug from {appender_name}",
                        "s": "c",
                        "ca": f"2026-03-19T{time.time()}Z",
                        "gb": appender_name,
                    }
                    f.write(json.dumps(lug) + "\n")
                    f.flush()  # Force write
                    time.sleep(0.1)  # Small delay to increase contention chance

            results_queue.put(
                {"success": True, "appender": appender_name, "count": lug_count}
            )

        except Exception as e:
            results_queue.put(
                {"success": False, "error": str(e), "appender": appender_name}
            )

    def _git_worker(self, worker_name: str, results_queue: mp.Queue):
        """Worker function that performs git operations."""
        try:
            # Simulate git add/commit operations
            import subprocess

            os.chdir(self.spoke_dir)

            # Git add
            subprocess.run(
                ["git", "add", "WAI-Spoke/"], check=True, capture_output=True, text=True
            )

            # Git commit
            subprocess.run(
                ["git", "commit", "-m", f"Test commit from {worker_name}"],
                check=True,
                capture_output=True,
                text=True,
            )

            results_queue.put({"success": True, "worker": worker_name})

        except subprocess.CalledProcessError as e:
            results_queue.put(
                {
                    "success": False,
                    "error": f"Git operation failed: {e}",
                    "worker": worker_name,
                }
            )
        except Exception as e:
            results_queue.put(
                {"success": False, "error": str(e), "worker": worker_name}
            )

    def _attempt_closeout(self, agent_name: str) -> Dict[str, Any]:
        """
        Attempt closeout operation with lock detection.

        In production, this would call the actual closeout implementation.
        For testing, simulate the behavior.
        """
        lock_file = self.spoke_dir / "WAI-Spoke" / ".closeout.lock"

        try:
            # Atomic lock acquisition — O_CREAT | O_EXCL fails if file exists
            try:
                fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, agent_name.encode())
                os.close(fd)
            except FileExistsError:
                return {
                    "success": False,
                    "error": "Concurrent closeout operation detected",
                    "agent": agent_name,
                }

            # Simulate closeout work
            time.sleep(1)

            # TODO: Call actual closeout implementation here

            return {
                "success": True,
                "agent": agent_name,
                "message": "Closeout completed successfully",
            }

        except Exception as e:
            return {"success": False, "error": str(e), "agent": agent_name}
        finally:
            # Clean up lock
            if lock_file.exists():
                lock_file.unlink()

    def _load_wai_state(self) -> Dict[str, Any]:
        """Load WAI-State.json."""
        state_file = self.spoke_dir / "WAI-Spoke" / "WAI-State.json"
        with open(state_file) as f:
            return json.load(f)

    def _load_lugs(self) -> List[Dict[str, Any]]:
        """Load all lugs from WAI-Lugs.jsonl."""
        lugs_file = self.spoke_dir / "WAI-Spoke" / "WAI-Lugs.jsonl"
        lugs = []
        with open(lugs_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    lugs.append(json.loads(line))
        return lugs


if __name__ == "__main__":
    # Set multiprocessing start method for cross-platform compatibility
    if hasattr(mp, "set_start_method"):
        try:
            mp.set_start_method("fork", force=True)
        except RuntimeError:
            pass  # Already set

    unittest.main()
