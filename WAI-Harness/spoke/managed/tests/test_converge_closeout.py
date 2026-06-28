#!/usr/bin/env python3
"""Acceptance tests for CSRP P6 convergent closeout (converge_closeout.py).

Maps 1:1 to impl-csrp-p6-convergent-closeout-v1 `verify`:
  - exactly one lead (lease lock; steals expired lease)
  - idle competitor -> reconciled + reaped -> single tree (no lost work)
  - ACTIVE competitor -> committed work merged, NEVER force-closed (worktree survives)
  - dead/dirty lane -> committed-to-branch then merged (no uncommitted loss)
  - single-session -> zero-cost no-op
  - signal/drain mailbox round-trip
  - unify-then-VERIFY: a RED unified tree blocks + RETAINS the lock (operator's gate)

Each test builds a throwaway git repo + real worktrees in a tempdir. Needs git on PATH.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import worktree_guard as wg  # noqa: E402
import converge_closeout as cc  # noqa: E402

BASE_REL = os.path.join("WAI-Harness", "spoke", "local")
GREEN = [sys.executable, "-c", "import sys;sys.exit(0)"]
RED = [sys.executable, "-c", "import sys;sys.exit(1)"]


def _git(repo, *args, check=True):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=check)


class ConvergeBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-test-")
        self.main = os.path.join(self.tmp, "spoke")
        os.makedirs(os.path.join(self.main, BASE_REL))
        _git(self.main, "init", "-q")
        _git(self.main, "config", "user.email", "t@t.t")
        _git(self.main, "config", "user.name", "t")
        open(os.path.join(self.main, "seed"), "w").close()
        _git(self.main, "add", "-A")
        _git(self.main, "commit", "-q", "-m", "seed")
        _git(self.main, "branch", "-M", "main")
        self.base = os.path.join(self.main, BASE_REL)

    def tearDown(self):
        subprocess.run(["rm", "-rf", self.tmp])

    def _worktree_with_commit(self, name, fname=None, content="x", commit=True):
        res = wg.session_worktree_new(self.main, name=name)
        wt = res["worktree"]
        if commit:
            fn = fname or f"{name}.txt"
            with open(os.path.join(wt, fn), "w") as f:
                f.write(content)
            _git(wt, "add", "-A")
            _git(wt, "commit", "-q", "-m", f"work on {name}")
        return wt

    def _register_lane(self, sid, worktree, age_seconds=0):
        reg = wg._load_registry(self.base)
        last = wg._utcnow() - timedelta(seconds=age_seconds)
        reg["lanes"][sid] = {"wai_session": worktree, "worktree": worktree,
                             "started_at": wg._iso(last), "last_seen": wg._iso(last),
                             "transcript": ""}
        wg._save_registry(self.base, reg)


class LockTests(ConvergeBase):
    def test_exactly_one_lead(self):
        a = cc.acquire_lock(self.base, "sidA")
        b = cc.acquire_lock(self.base, "sidB")
        self.assertTrue(a["acquired"])
        self.assertFalse(b["acquired"])
        self.assertEqual(b["holder"], "sidA")

    def test_release_then_acquire(self):
        cc.acquire_lock(self.base, "sidA")
        self.assertTrue(cc.release_lock(self.base, "sidA")["released"])
        self.assertTrue(cc.acquire_lock(self.base, "sidB")["acquired"])

    def test_steal_expired_lease(self):
        cc.acquire_lock(self.base, "sidA", lease_seconds=1)
        # force the lease into the past
        p = cc._lock_path(self.base)
        lk = json.loads(open(p).read())
        lk["lease_expires"] = wg._iso(wg._utcnow() - timedelta(seconds=10))
        open(p, "w").write(json.dumps(lk))
        b = cc.acquire_lock(self.base, "sidB")
        self.assertTrue(b["acquired"], "an expired lease must be steal-able (no deadlock on crash)")
        self.assertEqual(b["holder"], "sidB")

    def test_reentrant(self):
        cc.acquire_lock(self.base, "sidA")
        again = cc.acquire_lock(self.base, "sidA")
        self.assertTrue(again["acquired"] and again.get("reentrant"))


class MailboxTests(ConvergeBase):
    def test_signal_drain_roundtrip(self):
        cc.signal(self.base, "sidX", from_sid="me")
        d = cc.drain_signals(self.base, "sidX")
        self.assertEqual(d["count"], 1)
        self.assertEqual(d["requests"][0]["type"], "converge_request")
        self.assertEqual(cc.drain_signals(self.base, "sidX")["requests"], [])  # cleared

    def test_cooperative_self_converge_flow(self):
        # Mirrors the stop-hook Stage B: a signalled lane drains its request and
        # unregisters itself so the lead can reap it.
        self._register_lane("sidS", "laneS", age_seconds=600)
        cc.signal(self.base, "sidS", from_sid="lead")
        drained = cc.drain_signals(self.base, "sidS")
        self.assertEqual(drained["count"], 1)
        self.assertIn("sidS", wg.live_lanes(self.base))
        wg.lane_unregister(self.base, "sidS")
        self.assertNotIn("sidS", wg.live_lanes(self.base))


class ConvergeTests(ConvergeBase):
    def test_single_session_noop(self):
        out = cc.converge(self.base, "solo", repo=self.main)
        self.assertTrue(out["ok"])
        self.assertFalse(out["lead"])
        self.assertEqual(out["reason"], "no-competitors")

    def test_idle_competitor_converges_to_single_tree(self):
        self._worktree_with_commit("laneA")
        self._register_lane("sidA", "laneA", age_seconds=600)  # idle
        out = cc.converge(self.base, "me", repo=self.main, test_cmd=GREEN)
        self.assertTrue(out["ok"], out)
        self.assertTrue(out["lead"])
        self.assertIn("laneA", [c["name"] for c in out["converged"]])
        # single tree: worktree gone, branch merged + reaped, lane unregistered
        self.assertEqual(wg.session_worktrees(self.main), [])
        self.assertIn("work on laneA", _git(self.main, "log", "--oneline").stdout)
        self.assertNotIn("session/laneA", _git(self.main, "branch").stdout)  # branch reaped post-merge
        self.assertNotIn("sidA", wg.live_lanes(self.base))
        # work preserved on main
        self.assertTrue(os.path.exists(os.path.join(self.main, "laneA.txt")))
        self.assertTrue(out["verify"]["ok"])

    def test_active_competitor_not_force_closed(self):
        self._worktree_with_commit("laneB")
        self._register_lane("sidB", "laneB", age_seconds=5)  # ACTIVE (recent)
        out = cc.converge(self.base, "me", repo=self.main, test_cmd=GREEN)
        self.assertTrue(out["ok"], out)
        names_active = [c["name"] for c in out["reconciled_active"]]
        self.assertIn("laneB", names_active)
        # committed work merged into main...
        self.assertTrue(os.path.exists(os.path.join(self.main, "laneB.txt")))
        # ...but the live session's worktree + lane SURVIVE (never force-closed)
        self.assertIn("laneB", [w["name"] for w in wg.session_worktrees(self.main)])
        self.assertIn("sidB", wg.live_lanes(self.base))
        self.assertIn("sidB", out["signalled"])

    def test_dead_dirty_lane_committed_no_loss(self):
        wt = self._worktree_with_commit("laneD", commit=False)  # worktree, no commit
        with open(os.path.join(wt, "uncommitted.txt"), "w") as f:
            f.write("precious")
        self._register_lane("sidD", "laneD", age_seconds=wg.LANE_TTL_SECONDS + 100)  # dead
        out = cc.converge(self.base, "me", repo=self.main, test_cmd=GREEN)
        self.assertTrue(out["ok"], out)
        # the uncommitted work was committed-to-branch then merged — nothing lost
        self.assertTrue(os.path.exists(os.path.join(self.main, "uncommitted.txt")))
        self.assertEqual(open(os.path.join(self.main, "uncommitted.txt")).read(), "precious")

    def test_red_unified_tree_blocks_and_retains_lock(self):
        self._worktree_with_commit("laneE")
        self._register_lane("sidE", "laneE", age_seconds=600)
        out = cc.converge(self.base, "me", repo=self.main, test_cmd=RED)
        self.assertFalse(out["ok"], "a RED unified tree must NOT report ok")
        self.assertEqual(out["verify"]["status"], "RED")
        self.assertIn("lead_must_fix", out)
        # lock RETAINED for fix-forward (not released)
        self.assertEqual((cc._read_lock(self.base) or {}).get("holder_sid"), "me")

    def test_not_lead_when_lock_held(self):
        self._worktree_with_commit("laneF")
        self._register_lane("sidF", "laneF", age_seconds=600)
        cc.acquire_lock(self.base, "otherLead")  # someone else is already converging
        out = cc.converge(self.base, "me", repo=self.main, test_cmd=GREEN)
        self.assertTrue(out["ok"])
        self.assertFalse(out["lead"])
        self.assertEqual(out["reason"], "not-lead")
        self.assertEqual(out["lock_held_by"], "otherLead")
        # competitor untouched (the real lead will handle it)
        self.assertIn("laneF", [w["name"] for w in wg.session_worktrees(self.main)])


class TestAbsorptionCandidates(ConvergeBase):
    """s134 operator rule: a lane whose opening session is NOT open is an absorption
    candidate -- without waiting the 12h reap TTL."""

    def test_not_open_lane_is_candidate(self):
        self._register_lane("sidOpen", "laneOpen", age_seconds=10)
        self._register_lane("sidGone", "laneGone", age_seconds=cc.ACTIVE_WINDOW_S + 120)
        cands = cc.absorption_candidates(self.base, "sidOpen")
        self.assertEqual([c["sid"] for c in cands], ["sidGone"])

    def test_open_lane_not_candidate_and_self_excluded(self):
        self._register_lane("sidMe", "laneMe", age_seconds=10)
        self._register_lane("sidPeer", "lanePeer", age_seconds=10)
        self.assertEqual(cc.absorption_candidates(self.base, "sidMe"), [])

    def test_status_surfaces_candidates(self):
        self._register_lane("sidMe", "laneMe", age_seconds=10)
        self._register_lane("sidGone", "laneGone", age_seconds=cc.ACTIVE_WINDOW_S + 300)
        st = cc.status(self.base, "sidMe", repo=self.main)
        self.assertEqual([c["sid"] for c in st["absorption_candidates"]], ["sidGone"])

    def test_converge_absorbs_laneonly_not_open(self):
        self._register_lane("sidGone", "laneGone", age_seconds=cc.ACTIVE_WINDOW_S + 300)
        rep = cc.converge(self.base, "sidMe", repo=self.main, verify=False)
        self.assertIn("sidGone", [a["sid"] for a in rep["absorbed_laneonly"]])
        self.assertNotIn("sidGone", wg.live_lanes(self.base))


if __name__ == "__main__":
    unittest.main(verbosity=2)
