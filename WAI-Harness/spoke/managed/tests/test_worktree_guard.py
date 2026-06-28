#!/usr/bin/env python3
"""Tests for worktree_guard concurrent-session isolation.

Focus: the cross-worktree liveness contract (concurrent-session-autoisolation AC3).
A session launched inside a git worktree MUST see — and be seen by — the session in
the main tree, because the only real hazard is two sessions sharing one checkout. If
the lane registry were CWD-relative (the bug this guards), each worktree would keep a
divergent registry and the sessions would be invisible to each other, so the launcher
would never decide to isolate.

Runs standalone (`python3 test_worktree_guard.py`) or under pytest. No network; needs
git on PATH. Each test builds a throwaway repo + worktree in a tempdir.
"""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import worktree_guard as wg  # noqa: E402

BASE_REL = os.path.join("WAI-Harness", "spoke", "local")


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args],
                          capture_output=True, text=True, check=True)


def _init_repo(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")
    # a commit so worktree add has a HEAD to branch from
    open(os.path.join(root, "seed"), "w").close()
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")


class CrossWorktreeLiveness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wg-test-")
        self.main = os.path.join(self.tmp, "spoke")
        os.makedirs(os.path.join(self.main, BASE_REL))
        _init_repo(self.main)
        self.main_base = os.path.join(self.main, BASE_REL)

    def tearDown(self):
        subprocess.run(["rm", "-rf", self.tmp])

    def _make_worktree(self):
        res = wg.session_worktree_new(self.main, name="s-test")
        wt = res["worktree"]
        wt_base = os.path.join(wt, BASE_REL)
        os.makedirs(wt_base, exist_ok=True)
        return wt, wt_base

    def test_registry_path_reroots_worktree_to_main(self):
        """A worktree base resolves its registry path back onto the main tree."""
        _, wt_base = self._make_worktree()
        main_reg = wg._registry_path(self.main_base)
        wt_reg = wg._registry_path(wt_base)
        self.assertEqual(os.path.abspath(main_reg), os.path.abspath(wt_reg),
                         "worktree registry must resolve to the MAIN tree registry")
        self.assertTrue(os.path.abspath(main_reg).startswith(os.path.abspath(self.main) + os.sep))

    def test_two_lanes_across_worktrees_see_each_other(self):
        """Lane registered from the main tree and lane registered from inside a
        worktree both appear live from EITHER base — the launcher's isolate
        decision depends on this count being honest across worktrees."""
        wt, wt_base = self._make_worktree()
        a = wg.lane_register(self.main_base, "cc-main-0001")
        b = wg.lane_register(wt_base, "cc-wt-0002")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        # from the worktree's perspective, both lanes are live (count drives isolate)
        live_from_wt = wg.live_lanes(wt_base)
        live_from_main = wg.live_lanes(self.main_base)
        self.assertEqual(set(live_from_wt), {"cc-main-0001", "cc-wt-0002"})
        self.assertEqual(set(live_from_main), set(live_from_wt))
        # the second registration must have reported the first as an "other"
        self.assertIn("cc-main-0001", b["others"])
        self.assertEqual(b["others_count"], 1)

    def test_single_tree_base_unchanged(self):
        """No worktree -> _canonical_base must not rewrite the path (zero-cost path)."""
        self.assertEqual(os.path.abspath(wg._canonical_base(self.main_base)),
                         os.path.abspath(self.main_base))


if __name__ == "__main__":
    unittest.main(verbosity=2)
