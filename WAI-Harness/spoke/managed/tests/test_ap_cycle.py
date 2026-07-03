#!/usr/bin/env python3
"""Tests for ap_cycle pure logic — branch naming, cycle counting, start/finish plans."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ap_cycle as ac  # noqa: E402


def test_cycle_increment_and_branch_name():
    assert ac.next_cycle_number({}) == 1
    assert ac.next_cycle_number({"cycle": 7}) == 8
    assert ac.branch_name("mywheel", 3) == "ap/mywheel/cycle-3"
    assert ac.branch_name("weird/id name", 1) == "ap/weird-id-name/cycle-1"


def test_plan_start_clean_platform():
    p = ac.plan_start("mywheel", {"cycle": 4}, main_clean=True, main_ff=True, verify_ok=True)
    assert p["reconcile_ok"] and p["cycle"] == 5 and p["branch"] == "ap/mywheel/cycle-5"
    assert any("checkout -b ap/mywheel/cycle-5" in s for s in p["steps"])
    assert p["blockers"] == []


def test_plan_start_blocked_lists_reasons():
    p = ac.plan_start("s", {}, main_clean=False, main_ff=True, verify_ok=False)
    assert not p["reconcile_ok"] and p["steps"] == []
    assert any("uncommitted" in b for b in p["blockers"])
    assert any("verify" in b for b in p["blockers"])


def test_plan_finish_merge_on_pass():
    p = ac.plan_finish("ap/s/cycle-1", gate_passed=True, commits_ahead=3)
    assert p["action"] == "merge"
    assert any("merge --no-ff ap/s/cycle-1" in s for s in p["steps"])


def test_plan_finish_quarantine_on_fail():
    p = ac.plan_finish("ap/s/cycle-1", gate_passed=False, commits_ahead=3)
    assert p["action"] == "quarantine"  # NEVER merges a red branch; tracked dead-end


def test_plan_finish_noop_when_empty():
    p = ac.plan_finish("ap/s/cycle-1", gate_passed=True, commits_ahead=0)
    assert p["action"] == "noop"
