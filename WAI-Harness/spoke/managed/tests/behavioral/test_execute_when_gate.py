"""
Behavioral tests for evaluate_execute_when gate logic.

Tests all four execute_when variants using real file operations.
WAI_SPOKE_PATH is set per-test to isolate lug state.
"""

import json
import os
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _place_lug(spoke: Path, lug_id: str, status: str, lug_type: str = "task", extra: dict | None = None):
    """Write a minimal lug file at the given status path."""
    data = {"id": lug_id, "type": lug_type, "status": status, **(extra or {})}
    dest = spoke / "WAI-Spoke/lugs/bytype" / lug_type / status / f"{lug_id}.json"
    dest.write_text(json.dumps(data))


def _gate(spoke: Path, lug: dict, phases=None):
    """Import evaluate_execute_when with WAI_SPOKE_PATH pointed at tmp spoke."""
    os.environ["WAI_SPOKE_PATH"] = str(spoke / "WAI-Spoke")
    # Re-import to pick up env var (lug_utils reads it at module load; reload it)
    import importlib
    import tools.lug_utils as lu
    importlib.reload(lu)
    return lu.evaluate_execute_when(lug, phases)


# ── No gate ──────────────────────────────────────────────────────────────────

def test_no_execute_when_always_ready(tmp_spoke):
    ready, reason = _gate(tmp_spoke, {"id": "x", "type": "task"})
    assert ready is True
    assert reason == ""


def test_no_execute_when_blocked_by_open_lug(tmp_spoke):
    _place_lug(tmp_spoke, "dep-001", "open")
    lug = {"id": "x", "type": "task", "blocked_by": ["dep-001"]}
    ready, reason = _gate(tmp_spoke, lug)
    assert ready is False
    assert "dep-001" in reason


def test_no_execute_when_blocked_by_completed_lug(tmp_spoke):
    _place_lug(tmp_spoke, "dep-done", "completed")
    lug = {"id": "x", "type": "task", "blocked_by": ["dep-done"]}
    ready, reason = _gate(tmp_spoke, lug)
    assert ready is True


# ── manual_gate ───────────────────────────────────────────────────────────────

def test_manual_gate_always_blocks(tmp_spoke):
    lug = {"id": "x", "type": "task", "execute_when": {"manual_gate": True}}
    ready, reason = _gate(tmp_spoke, lug)
    assert ready is False
    assert "manual gate" in reason


def test_manual_gate_false_does_not_block(tmp_spoke):
    lug = {"id": "x", "type": "task", "execute_when": {"manual_gate": False}}
    ready, reason = _gate(tmp_spoke, lug)
    assert ready is True


# ── all_completed ─────────────────────────────────────────────────────────────

def test_all_completed_passes_when_all_done(tmp_spoke):
    _place_lug(tmp_spoke, "dep-a", "completed")
    _place_lug(tmp_spoke, "dep-b", "completed")
    lug = {"id": "x", "type": "task", "execute_when": {"all_completed": ["dep-a", "dep-b"]}}
    ready, reason = _gate(tmp_spoke, lug)
    assert ready is True


def test_all_completed_blocks_when_one_missing(tmp_spoke):
    _place_lug(tmp_spoke, "dep-a", "completed")
    _place_lug(tmp_spoke, "dep-b", "open")
    lug = {"id": "x", "type": "task", "execute_when": {"all_completed": ["dep-a", "dep-b"]}}
    ready, reason = _gate(tmp_spoke, lug)
    assert ready is False
    assert "dep-b" in reason


def test_all_completed_blocks_when_none_exist(tmp_spoke):
    lug = {"id": "x", "type": "task", "execute_when": {"all_completed": ["ghost-001"]}}
    ready, reason = _gate(tmp_spoke, lug)
    assert ready is False
    assert "ghost-001" in reason


# ── any_completed ─────────────────────────────────────────────────────────────

def test_any_completed_passes_when_one_done(tmp_spoke):
    _place_lug(tmp_spoke, "opt-a", "open")
    _place_lug(tmp_spoke, "opt-b", "completed")
    lug = {"id": "x", "type": "task", "execute_when": {"any_completed": ["opt-a", "opt-b"]}}
    ready, reason = _gate(tmp_spoke, lug)
    assert ready is True


def test_any_completed_blocks_when_none_done(tmp_spoke):
    _place_lug(tmp_spoke, "opt-a", "open")
    _place_lug(tmp_spoke, "opt-b", "open")
    lug = {"id": "x", "type": "task", "execute_when": {"any_completed": ["opt-a", "opt-b"]}}
    ready, reason = _gate(tmp_spoke, lug)
    assert ready is False
    assert "opt-a" in reason or "opt-b" in reason


# ── phase_completed ───────────────────────────────────────────────────────────

def test_phase_completed_passes_when_all_phase_members_done(tmp_spoke):
    _place_lug(tmp_spoke, "p1-task-a", "completed", extra={"phase": "p1-foundation"})
    _place_lug(tmp_spoke, "p1-task-b", "completed", extra={"phase": "p1-foundation"})
    lug = {"id": "x", "type": "task", "execute_when": {"phase_completed": "p1-foundation"}}
    ready, reason = _gate(tmp_spoke, lug, phases=[{"id": "p1-foundation"}])
    assert ready is True


def test_phase_completed_blocks_when_member_incomplete(tmp_spoke):
    _place_lug(tmp_spoke, "p1-task-a", "completed", extra={"phase": "p1-foundation"})
    _place_lug(tmp_spoke, "p1-task-b", "open", extra={"phase": "p1-foundation"})
    lug = {"id": "x", "type": "task", "execute_when": {"phase_completed": "p1-foundation"}}
    ready, reason = _gate(tmp_spoke, lug, phases=[{"id": "p1-foundation"}])
    assert ready is False
    assert "p1-foundation" in reason


def test_phase_completed_passes_when_no_members(tmp_spoke):
    """Empty phase (no lugs declare it) counts as complete."""
    lug = {"id": "x", "type": "task", "execute_when": {"phase_completed": "p-empty"}}
    ready, reason = _gate(tmp_spoke, lug, phases=[{"id": "p-empty"}])
    assert ready is True


# ── combined conditions ───────────────────────────────────────────────────────

def test_all_conditions_must_pass(tmp_spoke):
    """all_completed + manual_gate=False: both must pass."""
    _place_lug(tmp_spoke, "dep-x", "completed")
    lug = {
        "id": "x", "type": "task",
        "execute_when": {"all_completed": ["dep-x"], "manual_gate": False}
    }
    ready, _ = _gate(tmp_spoke, lug)
    assert ready is True


def test_manual_gate_overrides_satisfied_conditions(tmp_spoke):
    """manual_gate=True blocks even when all_completed passes."""
    _place_lug(tmp_spoke, "dep-x", "completed")
    lug = {
        "id": "x", "type": "task",
        "execute_when": {"all_completed": ["dep-x"], "manual_gate": True}
    }
    ready, reason = _gate(tmp_spoke, lug)
    assert ready is False
    assert "manual gate" in reason
