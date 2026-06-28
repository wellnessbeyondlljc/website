"""Tests for fleet_hygiene_scan.py — fleet hygiene scanner + session triage."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import fleet_hygiene_scan as fh  # noqa: E402


# ── classify_session ──────────────────────────────────────────────────────────

def _write_track(path, entries):
    Path(path).write_text("\n".join(json.dumps(e) for e in entries))


def test_classify_missing_track_is_husk(tmp_path):
    assert fh.classify_session(tmp_path / "nonexistent.jsonl") == "husk"


def test_classify_empty_track_is_husk(tmp_path):
    f = tmp_path / "track.jsonl"
    f.write_text("")
    assert fh.classify_session(f) == "husk"


def test_classify_only_session_start_is_husk(tmp_path):
    f = tmp_path / "track.jsonl"
    _write_track(f, [{"event": "session_start"}])
    assert fh.classify_session(f) == "husk"


def test_classify_closeout_event_is_closed(tmp_path):
    f = tmp_path / "track.jsonl"
    _write_track(f, [{"event": "session_start"}, {"p": 1, "event": "work"}, {"event": "closeout"}])
    assert fh.classify_session(f) == "closed"


def test_classify_completed_true_last_entry_is_closed(tmp_path):
    f = tmp_path / "track.jsonl"
    _write_track(f, [{"event": "session_start"}, {"event": "turn", "completed": True}])
    assert fh.classify_session(f) == "closed"


def test_classify_real_work_no_closeout_is_interrupted(tmp_path):
    f = tmp_path / "track.jsonl"
    _write_track(f, [{"event": "session_start"}, {"event": "turn", "p": 1, "completed": None}])
    assert fh.classify_session(f) == "interrupted"


def test_classify_skips_bad_json_lines(tmp_path):
    f = tmp_path / "track.jsonl"
    f.write_text('{"event": "session_start"}\nnot json\n{"event": "closeout"}\n')
    assert fh.classify_session(f) == "closed"


# ── scan_spoke_sessions ───────────────────────────────────────────────────────

def _make_spoke(tmp_path):
    """Create a minimal v4 spoke tree."""
    base = tmp_path / "WAI-Harness" / "spoke" / "local"
    (base / "WAI-State.json").parent.mkdir(parents=True, exist_ok=True)
    (base / "WAI-State.json").write_text("{}")
    sessions = base / "sessions"
    sessions.mkdir()
    return tmp_path, base, sessions


def test_scan_empty_sessions_dir(tmp_path):
    root, base, sessions = _make_spoke(tmp_path)
    rep = fh.scan_spoke_sessions(root)
    assert rep["husk_archived"] == 0
    assert rep["review_queued"] == 0


def test_scan_husk_below_grace_kept(tmp_path):
    root, base, sessions = _make_spoke(tmp_path)
    sess = sessions / "session-20260101-0000"
    sess.mkdir()
    (sess / "track.jsonl").write_text("")
    rep = fh.scan_spoke_sessions(root, grace_hours=24 * 365)  # huge grace = never archive
    assert rep["kept"] == 1
    assert rep["husk_archived"] == 0


def test_scan_husk_above_grace_counts(tmp_path):
    root, base, sessions = _make_spoke(tmp_path)
    sess = sessions / "session-20260101-0000"
    sess.mkdir()
    (sess / "track.jsonl").write_text("")
    # set mtime far in the past
    old = 0
    os.utime(sess, (old, old))
    rep = fh.scan_spoke_sessions(root, grace_hours=1)
    assert rep["husk_archived"] == 1


def test_scan_interrupted_queued(tmp_path):
    root, base, sessions = _make_spoke(tmp_path)
    sess = sessions / "session-20260101-0000"
    sess.mkdir()
    track = sess / "track.jsonl"
    _write_track(track, [{"event": "session_start"}, {"event": "turn", "p": 1}])
    rep = fh.scan_spoke_sessions(root, grace_hours=0)
    assert rep["review_queued"] == 1
    assert "session-20260101-0000" in rep["interrupted"]


def test_scan_interrupted_writes_review_queue_artifact(tmp_path):
    root, base, sessions = _make_spoke(tmp_path)
    sess = sessions / "session-20260601-1200"
    sess.mkdir()
    track = sess / "track.jsonl"
    _write_track(track, [{"event": "session_start"}, {"event": "turn", "p": 1}])
    rep = fh.scan_spoke_sessions(root, grace_hours=0)
    assert rep.get("review_queue_artifact")
    artifact = json.loads(Path(rep["review_queue_artifact"]).read_text())
    assert artifact["count"] == 1
    assert artifact["sessions"][0]["id"] == "session-20260601-1200"


def test_scan_closed_session_kept(tmp_path):
    root, base, sessions = _make_spoke(tmp_path)
    sess = sessions / "session-20260101-0000"
    sess.mkdir()
    _write_track(sess / "track.jsonl",
                 [{"event": "session_start"}, {"event": "closeout"}])
    rep = fh.scan_spoke_sessions(root, grace_hours=0)
    assert rep["kept"] == 1
    assert rep["review_queued"] == 0
    assert rep["husk_archived"] == 0


# ── rescue_worktrees ──────────────────────────────────────────────────────────

def test_rescue_dry_run_lists_without_executing(tmp_path):
    stranded = [
        {"path": str(tmp_path / "wt1"), "branch": "agent-abc123", "dirty": 5,
         "commits_ahead_of_main": "0", "locked": True, "stranded_uncommitted": True,
         "last_modified": None},
    ]
    with patch.object(fh, "_live_session_pids", return_value=set()):
        manifest = fh.rescue_worktrees(str(tmp_path), stranded, dry_run=True)
    assert manifest["dry_run"] is True
    assert len(manifest["rescued"]) == 1
    assert manifest["rescued"][0]["action"] == "would commit + prune (dry-run)"


def test_rescue_aborts_when_live_session_detected(tmp_path):
    stranded = [
        {"path": str(tmp_path / "wt1"), "branch": "agent-abc", "dirty": 3,
         "commits_ahead_of_main": "0", "locked": True, "stranded_uncommitted": True,
         "last_modified": None},
    ]
    with patch.object(fh, "_live_session_pids", return_value={12345}):
        manifest = fh.rescue_worktrees(str(tmp_path), stranded, dry_run=False)
    assert manifest["live_session_guard_triggered"] is True
    assert manifest["rescued"] == []
    assert "ABORTED" in manifest.get("note", "")


def test_rescue_skips_main_branch(tmp_path):
    stranded = [
        {"path": str(tmp_path / "wt1"), "branch": "main", "dirty": 2,
         "commits_ahead_of_main": "0", "locked": True, "stranded_uncommitted": True,
         "last_modified": None},
    ]
    with patch.object(fh, "_live_session_pids", return_value=set()):
        manifest = fh.rescue_worktrees(str(tmp_path), stranded, dry_run=False)
    assert len(manifest["skipped"]) == 1
    assert "main" in manifest["skipped"][0]["reason"]


# ── fleet scan (registry-based) ───────────────────────────────────────────────

def _make_registry(tmp_path, wheels):
    reg_path = tmp_path / "hub-registry.json"
    reg_path.write_text(json.dumps({"wheels": wheels}))
    return str(reg_path)


def test_fleet_scan_missing_path_counted(tmp_path):
    reg = _make_registry(tmp_path, [
        {"wheel_id": "ghost", "path": str(tmp_path / "nonexistent")},
    ])
    report, _ = fh.scan_fleet(reg, out_dir=str(tmp_path / "out"))
    assert report["totals"]["missing_path"] == 1
    assert report["totals"]["wheels"] == 1


def test_fleet_scan_wheel_with_no_worktrees(tmp_path):
    wheel = tmp_path / "mywheel"
    wheel.mkdir()
    # init a bare-ish git repo so _git calls don't error badly
    subprocess.run(["git", "init", str(wheel)], capture_output=True)
    subprocess.run(["git", "-C", str(wheel), "commit", "--allow-empty", "-m", "init"],
                   capture_output=True)
    reg = _make_registry(tmp_path, [{"wheel_id": "mywheel", "path": str(wheel)}])
    report, _ = fh.scan_fleet(reg, out_dir=str(tmp_path / "out"))
    assert report["totals"]["stranded_worktrees"] == 0
    wh = next(w for w in report["wheels"] if w["wheel_id"] == "mywheel")
    assert wh["agent_worktrees"] == 0


def test_fleet_scan_writes_json_report(tmp_path):
    reg = _make_registry(tmp_path, [
        {"wheel_id": "ghost", "path": str(tmp_path / "nonexistent")},
    ])
    out_dir = str(tmp_path / "out")
    report, _ = fh.scan_fleet(reg, out_dir=out_dir)
    files = os.listdir(out_dir)
    hygiene_files = [f for f in files if f.startswith("fleet-hygiene-")]
    assert len(hygiene_files) == 1
    saved = json.loads(open(os.path.join(out_dir, hygiene_files[0])).read())
    assert saved["totals"]["wheels"] == 1


def test_fleet_scan_rescue_dry_run_no_rescue_manifest(tmp_path):
    """When there are no stranded worktrees, no rescue manifest is written."""
    reg = _make_registry(tmp_path, [
        {"wheel_id": "ghost", "path": str(tmp_path / "nonexistent")},
    ])
    out_dir = str(tmp_path / "out")
    report, rescue = fh.scan_fleet(reg, out_dir=out_dir, rescue=True)
    assert rescue == {}  # no stranded worktrees -> no rescue manifest


# ── CLI smoke test ────────────────────────────────────────────────────────────

def test_cli_spoke_json(tmp_path):
    root, base, sessions = _make_spoke(tmp_path)
    result = fh.main(["--spoke", str(root), "--json"])
    assert result == 0


def test_cli_fleet_json(tmp_path):
    reg = _make_registry(tmp_path, [
        {"wheel_id": "ghost", "path": str(tmp_path / "nonexistent")},
    ])
    out_dir = str(tmp_path / "out")
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fh.main(["fleet", "--registry", reg, "--json", "--out-dir", out_dir])
    assert rc == 0
    parsed = json.loads(buf.getvalue())
    assert "report" in parsed


# subprocess import needed by test_fleet_scan_wheel_with_no_worktrees
import subprocess  # noqa: E402 (needed after the test body uses it)
