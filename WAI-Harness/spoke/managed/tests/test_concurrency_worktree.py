#!/usr/bin/env python3
"""Verification test for impl-concurrency-worktree-v1 (test-at-birth).

Covers verify[]: single-session=zero-cost (no worktree); detected-concurrency creates an
isolated worktree + mapping; orphan reap; reconciliation notice to the owning live session
(not the committer). Worktree ops run in a TEMP git repo (never the live tree).
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _temp_git_repo(d):
    subprocess.run(["git", "-C", d, "init", "-q"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", d, "config", "user.name", "t"], check=True)
    open(os.path.join(d, "f.txt"), "w").write("x")
    subprocess.run(["git", "-C", d, "add", "-A"], check=True)
    subprocess.run(["git", "-C", d, "commit", "-qm", "init"], check=True)


def test_single_session_zero_cost():
    wg = _load("worktree_guard")
    with tempfile.TemporaryDirectory() as d:
        _temp_git_repo(d)
        mp = os.path.join(d, "map.json")
        wt = wg.ensure_worktree("s1", d, mapping_path=mp, live_ids=["s1"])
        assert wt is None, "single session must NOT create a worktree (zero cost)"
        assert not os.path.exists(os.path.join(d, ".worktrees"))


def test_detected_concurrency_isolates_and_reaps():
    wg = _load("worktree_guard")
    with tempfile.TemporaryDirectory() as d:
        _temp_git_repo(d)
        mp = os.path.join(d, "map.json")
        # second live session present -> isolate s2
        wt = wg.ensure_worktree("s2", d, mapping_path=mp, live_ids=["s1", "s2"])
        assert wt and os.path.isdir(wt), "detected concurrency must create a worktree"
        assert json.load(open(mp)).get("s2") == wt, "mapping recorded"
        # s2 no longer live -> reaped
        reaped = wg.reap_orphans(d, mapping_path=mp, live_ids=["s1"])
        assert "s2" in reaped and "s2" not in json.load(open(mp)), "orphan worktree reaped"


def test_reconcile_notice_to_owner_not_committer():
    dw = _load("db_writer"); fr = _load("file_reconcile")
    with tempfile.TemporaryDirectory() as d:
        jr = os.path.join(d, "j.jsonl")
        notified = fr.emit_notices("synthesize_turn.py", "s1", ["s1", "s2"],
                                   {"synthesize_turn.py": "s2"}, commit_sha="abc", journal_path=jr)
        assert notified == ["s2"], f"only the owning live session s2 notified, got {notified}"
        events = [json.loads(l) for l in open(jr)]
        assert len(events) == 1 and events[0]["type"] == "file_update_notice"
        assert events[0]["session"] == "s2" and events[0]["status"] == "needs_reconcile"
        # committer is never self-notified
        assert all(e["session"] != "s1" for e in events)


if __name__ == "__main__":
    test_single_session_zero_cost();                print("PASS test_single_session_zero_cost")
    test_detected_concurrency_isolates_and_reaps(); print("PASS test_detected_concurrency_isolates_and_reaps")
    test_reconcile_notice_to_owner_not_committer(); print("PASS test_reconcile_notice_to_owner_not_committer")
    print("ALL PASS")
