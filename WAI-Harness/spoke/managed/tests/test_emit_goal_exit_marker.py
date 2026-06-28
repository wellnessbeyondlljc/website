"""Tests for tools/emit_goal_exit_marker.py — Session Exit: Outstanding Goal Marker."""

import importlib.util
import json
from pathlib import Path

_TOOL = Path(__file__).resolve().parent.parent / "tools" / "emit_goal_exit_marker.py"
_spec = importlib.util.spec_from_file_location("emit_goal_exit_marker", _TOOL)
egm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(egm)


def _write_track(base: Path, sid: str, events: list) -> Path:
    track = base / "sessions" / sid / "track.jsonl"
    track.parent.mkdir(parents=True, exist_ok=True)
    track.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return track


def test_outstanding_goal_writes_marker(tmp_path):
    sid = "session-20260624-1200"
    _write_track(tmp_path, sid, [
        {"event": "goal_set", "goal_id": "g1"},
        {"event": "goal_set", "goal_id": "g2"},
        {"event": "goal_completed", "goal_id": "g1"},
    ])

    summary = egm.emit_goal_exit_marker(str(tmp_path), session_id=sid)

    assert summary["status"] == "ok"
    assert summary["marker_written"] is True
    assert summary["outstanding"] == ["g2"]

    buf = tmp_path / "runtime" / "track-buffer.json"
    assert buf.exists()
    marker = json.loads(buf.read_text().strip())
    assert marker["event"] == "session_exit_with_goals"
    assert marker["outstanding"] == ["g2"]
    assert "ts" in marker


def test_all_goals_completed_no_marker(tmp_path):
    sid = "session-20260624-1300"
    _write_track(tmp_path, sid, [
        {"event": "goal_set", "goal_id": "g1"},
        {"event": "goal_completed", "goal_id": "g1"},
    ])

    summary = egm.emit_goal_exit_marker(str(tmp_path), session_id=sid)

    assert summary["status"] == "noop"
    assert summary["reason"] == "no_outstanding_goals"
    assert summary["marker_written"] is False
    assert not (tmp_path / "runtime" / "track-buffer.json").exists()


def test_no_goals_set_no_marker(tmp_path):
    sid = "session-20260624-1400"
    _write_track(tmp_path, sid, [
        {"event": "session_start"},
        {"event": "tool_use"},
    ])

    summary = egm.emit_goal_exit_marker(str(tmp_path), session_id=sid)

    assert summary["status"] == "noop"
    assert summary["outstanding"] == []
    assert summary["marker_written"] is False


def test_no_track_is_noop(tmp_path):
    summary = egm.emit_goal_exit_marker(str(tmp_path), session_id="missing-session")
    assert summary["status"] == "noop"
    assert summary["reason"] == "no_track"
    assert summary["marker_written"] is False


def test_session_id_from_guard(tmp_path):
    sid = "session-20260624-1500"
    guard = tmp_path / "runtime" / "session-guard.json"
    guard.parent.mkdir(parents=True, exist_ok=True)
    guard.write_text(json.dumps({"session_id": sid}))
    _write_track(tmp_path, sid, [
        {"event": "goal_set", "goal_id": "gA"},
    ])

    summary = egm.emit_goal_exit_marker(str(tmp_path))  # no explicit session id

    assert summary["session_id"] == sid
    assert summary["outstanding"] == ["gA"]
    assert summary["marker_written"] is True


def test_no_session_id_is_noop(tmp_path):
    # No guard file, no explicit session id -> no-op
    summary = egm.emit_goal_exit_marker(str(tmp_path))
    assert summary["status"] == "noop"
    assert summary["reason"] == "no_session_id"
    assert summary["marker_written"] is False
