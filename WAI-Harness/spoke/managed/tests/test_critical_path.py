#!/usr/bin/env python3
"""Tests for critical_path — blocker leverage ranking + transitive unblock counting."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import critical_path as cp  # noqa: E402


def test_direct_and_transitive_leverage():
    # K blocks A,B; A blocks C. K completing unblocks A,B (direct) and transitively C.
    lugs = [
        {"id": "K"},
        {"id": "A", "blocked_by": ["K"]},
        {"id": "B", "blocked_by": ["K"]},
        {"id": "C", "blocked_by": ["A"]},
    ]
    rows = cp.blocker_leverage(lugs, completed=set())
    top = rows[0]
    assert top["blocker"] == "K"
    assert top["direct_unblocks"] == 2  # A, B
    assert top["total_unblocks"] == 3   # A, B, C (transitive)
    assert top["dispatchable_now"] is True  # K has no blockers


def test_dispatchable_blocker_wins_tie():
    # X and Y each unblock 1; X is dispatchable, Y is itself blocked -> X ranks first.
    lugs = [
        {"id": "X"},
        {"id": "Y", "blocked_by": ["Z"]},
        {"id": "Z"},
        {"id": "a", "blocked_by": ["X"]},
        {"id": "b", "blocked_by": ["Y"]},
    ]
    rows = cp.blocker_leverage(lugs, completed=set())
    # Z unblocks Y->b transitively (2); X unblocks a (1). Z should top, both dispatchable.
    assert rows[0]["blocker"] == "Z"
    assert rows[0]["total_unblocks"] == 2


def test_resolved_blocker_ignored():
    lugs = [{"id": "A", "blocked_by": ["DONE"]}]
    rows = cp.blocker_leverage(lugs, completed={"DONE"})
    assert rows == []  # blocker already completed -> no leverage rows
