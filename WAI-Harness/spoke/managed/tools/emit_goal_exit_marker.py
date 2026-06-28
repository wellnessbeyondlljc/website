#!/usr/bin/env python3
"""
emit_goal_exit_marker.py — Session Exit: Outstanding Goal Marker.

Faithful extraction of wai-closeout.md section "10e. Session Exit — Outstanding
Goal Marker". If any goals were set this session via ``goal_set`` events and not
all were completed, write a ``session_exit_with_goals`` event to the runtime
track-buffer so the next session (or Ozi) can detect and recover outstanding work.

Behavior (mirrors the ceremony block exactly):
  1. Resolve the current session id. Either from --session-id, or by reading
     {BASE}/runtime/session-guard.json -> .session_id. If empty, exit 0 (no-op).
  2. Read {BASE}/sessions/{SID}/track.jsonl. If missing, exit 0 (no-op).
  3. Scan track events: collect goal_set goal_ids and goal_completed goal_ids.
  4. outstanding = goal_set ids not in goal_completed. If none, exit 0 (no-op).
  5. Else write a session_exit_with_goals marker line to
     {BASE}/runtime/track-buffer.json (Stop hook will commit it).

CLI:
  python3 emit_goal_exit_marker.py --base BASE [--session-id SID]

Prints a short JSON summary to stdout.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def emit_goal_exit_marker(base: str, session_id: str = "") -> dict:
    """Run the outstanding-goal-marker logic. Returns a summary dict."""
    base_path = Path(base)

    current_session_id = session_id or ""
    if not current_session_id:
        guard_path = base_path / "runtime" / "session-guard.json"
        try:
            current_session_id = json.load(open(guard_path)).get("session_id", "")
        except Exception:
            current_session_id = ""

    if not current_session_id:
        return {"status": "noop", "reason": "no_session_id", "outstanding": [], "marker_written": False}

    track_path = base_path / "sessions" / current_session_id / "track.jsonl"
    if not track_path.exists():
        return {
            "status": "noop",
            "reason": "no_track",
            "session_id": current_session_id,
            "outstanding": [],
            "marker_written": False,
        }

    goals_set = {}
    goals_done = set()
    for raw in track_path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except Exception:
            continue
        ev = entry.get("event", "")
        if ev == "goal_set":
            gid = entry.get("goal_id", "")
            if gid:
                goals_set[gid] = entry
        elif ev == "goal_completed":
            gid = entry.get("goal_id", "")
            if gid:
                goals_done.add(gid)

    outstanding = [gid for gid in goals_set if gid not in goals_done]
    if not outstanding:
        return {
            "status": "noop",
            "reason": "no_outstanding_goals",
            "session_id": current_session_id,
            "outstanding": [],
            "marker_written": False,
        }

    marker = json.dumps({
        "event": "session_exit_with_goals",
        "outstanding": outstanding,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    buffer_path = base_path / "runtime" / "track-buffer.json"
    buffer_path.parent.mkdir(parents=True, exist_ok=True)
    buffer_path.write_text(marker + "\n")

    return {
        "status": "ok",
        "session_id": current_session_id,
        "outstanding": outstanding,
        "marker_written": True,
        "marker_path": str(buffer_path),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Emit outstanding-goal session-exit marker.")
    parser.add_argument("--base", required=True, help="BASE state directory (the resolved v4/v3 base)")
    parser.add_argument("--session-id", default="", help="Session id (else read from runtime/session-guard.json)")
    args = parser.parse_args(argv)

    summary = emit_goal_exit_marker(args.base, args.session_id)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
