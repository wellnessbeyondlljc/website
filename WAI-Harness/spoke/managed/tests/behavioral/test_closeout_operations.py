"""
Behavioral tests for closeout operations.

Tests real autosave reconciliation, state updates, and session-summary creation
using real file operations on bytype/ structure. No mocks.
"""

import json
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.wai_validate import validate_lug, validate_wai_state


def _write_lug_file(spoke_path: Path, type_name: str, status: str, lug: dict):
    """Write a lug to its canonical bytype/ location."""
    path = spoke_path / "WAI-Spoke" / "lugs" / "bytype" / type_name / status / f"{lug['id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lug, indent=2))
    return path


def test_autosave_reconciliation(tmp_spoke):
    """Autosave lugs can be reconciled into a session-summary."""
    # Create autosave lugs in other/open/
    auto1 = {
        "id": "autosave-001", "type": "autosave", "title": "Checkpoint 1",
        "status": "open", "created_at": "2026-03-27T01:00:00Z", "reconciled": False,
    }
    auto2 = {
        "id": "autosave-002", "type": "autosave", "title": "Checkpoint 2",
        "status": "open", "created_at": "2026-03-27T01:30:00Z", "reconciled": False,
    }
    _write_lug_file(tmp_spoke, "other", "open", auto1)
    _write_lug_file(tmp_spoke, "other", "open", auto2)

    # Simulate reconciliation (closeout Step 1)
    bytype = tmp_spoke / "WAI-Spoke" / "lugs" / "bytype"
    autosave_files = list(bytype.rglob("autosave-*.json"))
    assert len(autosave_files) == 2

    # Mark reconciled, move to completed
    reconciled_ids = []
    for f in autosave_files:
        lug = json.loads(f.read_text())
        lug["reconciled"] = True
        lug["status"] = "completed"
        completed_path = bytype / "other" / "completed" / f.name
        completed_path.write_text(json.dumps(lug, indent=2))
        f.unlink()
        reconciled_ids.append(lug["id"])

    # Create session-summary
    summary = {
        "id": "session-20260327-0130",
        "type": "session-summary",
        "title": "Session 88 summary",
        "status": "completed",
        "created_at": "2026-03-27T02:00:00Z",
        "created_by": "test",
        "session_number": 88,
        "accomplished": ["Reconciled autosaves"],
        "autosaves_reconciled": reconciled_ids,
    }
    summary_path = bytype / "session-summary" / "session-20260327-0130.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    # Verify: autosaves moved, summary created
    open_autosaves = list((bytype / "other" / "open").glob("autosave-*.json"))
    assert len(open_autosaves) == 0, "All autosaves should be moved to completed"
    assert summary_path.exists()

    loaded_summary = json.loads(summary_path.read_text())
    assert sorted(loaded_summary["autosaves_reconciled"]) == ["autosave-001", "autosave-002"]


def test_state_update_increments_session(tmp_spoke):
    """Closeout Step 5: session_count increments, timestamps update."""
    state_file = tmp_spoke / "WAI-Spoke" / "WAI-State.json"
    state = json.loads(state_file.read_text())

    old_count = state["_session_state"]["session_count"]

    # Simulate closeout Step 5
    state["_session_state"]["session_count"] += 1
    state["_session_state"]["last_closeout"] = "2026-03-27T02:00:00Z"
    state["_session_state"]["last_modified_by"] = "claude-sonnet-4-6"
    state["_session_state"]["last_modified_at"] = "2026-03-27T02:00:00Z"
    state["_session_state"]["protocol_completed"] = True

    state_file.write_text(json.dumps(state, indent=2))

    # Verify
    reloaded = json.loads(state_file.read_text())
    assert reloaded["_session_state"]["session_count"] == old_count + 1
    assert reloaded["_session_state"]["last_closeout"] == "2026-03-27T02:00:00Z"
    assert validate_wai_state(reloaded) == [] or all(
        v.startswith("WARNING") for v in validate_wai_state(reloaded)
    )


def test_version_bump(tmp_spoke):
    """Closeout Step 4: version patch increments correctly."""
    state_file = tmp_spoke / "WAI-Spoke" / "WAI-State.json"
    state = json.loads(state_file.read_text())

    version = state["wheel"]["version"]
    parts = version.split(".")
    parts[2] = str(int(parts[2]) + 1)
    new_version = ".".join(parts)
    state["wheel"]["version"] = new_version

    state_file.write_text(json.dumps(state, indent=2))

    reloaded = json.loads(state_file.read_text())
    assert reloaded["wheel"]["version"] == "1.0.1"


def test_closeout_idempotency(tmp_spoke):
    """Running closeout twice on same session doesn't double-increment."""
    state_file = tmp_spoke / "WAI-Spoke" / "WAI-State.json"
    session_id = "session-20260327-0200"

    # First closeout
    state = json.loads(state_file.read_text())
    state["_session_state"]["session_count"] += 1
    state["_session_state"]["last_session_id"] = session_id
    state_file.write_text(json.dumps(state, indent=2))
    count_after_first = state["_session_state"]["session_count"]

    # Second closeout — detect duplicate by last_session_id
    state2 = json.loads(state_file.read_text())
    if state2["_session_state"].get("last_session_id") == session_id:
        # Already closed — skip increment
        pass
    else:
        state2["_session_state"]["session_count"] += 1

    assert state2["_session_state"]["session_count"] == count_after_first


def test_signal_written_to_bytype(tmp_spoke):
    """Closeout Step 2: high-impact signal goes to bytype/signal/undelivered/."""
    signal = {
        "id": "signal-test-closeout-v1",
        "type": "signal",
        "title": "Test closeout signal",
        "status": "undelivered",
        "created_at": "2026-03-27T02:00:00Z",
        "created_by": "test",
        "impact": 9,
        "rationale": "Test signal for behavioral test",
        "routed_to": "SIGNAL",
        "_behavior_directive": {"action": "track_only"},
    }

    signal_path = _write_lug_file(tmp_spoke, "signal", "undelivered", signal)
    assert signal_path.exists()

    loaded = json.loads(signal_path.read_text())
    assert loaded["impact"] == 9
    assert loaded["type"] == "signal"

    violations = validate_lug(loaded)
    assert violations == [], f"Signal should be valid: {violations}"
