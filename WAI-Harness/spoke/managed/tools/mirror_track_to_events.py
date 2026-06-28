#!/usr/bin/env python3
"""
mirror_track_to_events.py — Mirror session track entries to activity_events.

Reads WAI-Spoke/sessions/<session_id>/track.jsonl and posts tool_call-class events
to the Supabase activity_events table. Deduplicated on (session_id, event, ts) to
prevent double-posting on retry.

Usage:
  python3 tools/mirror_track_to_events.py --session-id <id> [--dry-run]
  python3 tools/mirror_track_to_events.py --track-path <path> [--dry-run]

Called automatically from closeout skill after session_end event is emitted.
"""

import json
import os
import sys
import argparse
import datetime

_HERE      = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)

# Resolve the active spoke working base (v4: WAI-Harness/spoke/local; v3: WAI-Spoke).
# _REPO_ROOT is WAI-Harness/spoke/managed, so the spoke root is three dirnames up.
sys.path.insert(0, _HERE)
from wai_paths import resolve_wai_root  # noqa: E402  harness-mode root resolver

_SPOKE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_REPO_ROOT)))
_root, _mode = resolve_wai_root(_SPOKE_ROOT)
_BASE = _root if (_root and _mode != "none") else os.path.join(_SPOKE_ROOT, "WAI-Spoke")

# Tool names that map to interesting activity event types
_TOOL_CATEGORY_MAP = {
    "Edit":         "code_edit",
    "Write":        "code_write",
    "Bash":         "shell_exec",
    "Read":         "file_read",
    "Agent":        "agent_dispatch",
    "WebFetch":     "web_fetch",
    "WebSearch":    "web_search",
    "TaskCreate":   "task_create",
    "TaskUpdate":   "task_update",
}

# Work category heuristic (rough pass; refined by Group 5 Assessor later)
def _work_category(event: dict, tool_name: str | None) -> list[str]:
    categories = []
    note = str(event.get("note", "") or "").lower()
    lug_id = str(event.get("lug_id", "") or "").lower()

    if "bug" in lug_id or "fix" in note:
        categories.append("bug_fix")
    if tool_name in ("Read", "WebSearch", "WebFetch"):
        categories.append("research")
    if tool_name in ("Edit", "Write"):
        categories.append("code_change")
    if event.get("event") == "lug_completed":
        categories.append("lug_lifecycle")

    return categories or ["general"]


def _extract_tool_name(event: dict) -> str | None:
    """Try to infer tool name from event fields."""
    action = event.get("action") or event.get("tool") or event.get("tool_name")
    if action:
        for tool in _TOOL_CATEGORY_MAP:
            if tool.lower() in str(action).lower():
                return tool
    return None


def track_to_activity_rows(
    track_path: str,
    wheel_id: str,
    session_id: str,
    parent_event_id: str | None = None,
) -> list[dict]:
    """Convert track.jsonl entries to activity_events rows."""
    rows = []

    try:
        lines = open(track_path).readlines()
    except FileNotFoundError:
        print(f"[mirror_track] Track not found: {track_path}", file=sys.stderr)
        return rows

    seen = set()  # dedup on (event, ts)

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = ev.get("event", "")
        ts = ev.get("ts") or ev.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat()
        dedup_key = (event_type, ts)

        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        tool_name = _extract_tool_name(ev)
        work_cats = _work_category(ev, tool_name)

        row = {
            "event_type":      event_type,
            "ts":              ts,
            "wheel_id":        wheel_id,
            "session_id":      session_id,
            "session_kind":    ev.get("session_kind", "user"),
            "tool_name":       tool_name,
            "work_category":   work_cats,
            "outcome":         ev.get("outcome"),
            "lug_refs":        json.dumps([ev["lug_id"]]) if ev.get("lug_id") else None,
            "parent_event_id": parent_event_id,
            "metadata":        json.dumps({k: v for k, v in ev.items()
                                           if k not in ("event", "ts", "timestamp", "lug_id", "outcome")}),
        }
        rows.append(row)

    return rows


def main():
    parser = argparse.ArgumentParser(description="Mirror track.jsonl to activity_events")
    parser.add_argument("--session-id", help="Session ID (locates track automatically)")
    parser.add_argument("--track-path", help="Explicit path to track.jsonl")
    parser.add_argument("--wheel-id", default=os.environ.get("WHEEL_ID", ""), help="Spoke wheel_id")
    parser.add_argument("--parent-event-id", help="UUID of the session_start activity_events row")
    parser.add_argument("--dry-run", action="store_true", help="Print rows without posting")
    args = parser.parse_args()

    # Resolve track path
    track_path = args.track_path
    if not track_path and args.session_id:
        track_path = os.path.join(_BASE, "sessions", args.session_id, "track.jsonl")

    if not track_path:
        # Try latest session
        sessions_dir = os.path.join(_BASE, "sessions")
        if os.path.isdir(sessions_dir):
            sessions = sorted(os.listdir(sessions_dir), reverse=True)
            if sessions:
                track_path = os.path.join(sessions_dir, sessions[0], "track.jsonl")
                if not args.session_id:
                    args.session_id = sessions[0]

    if not track_path or not os.path.exists(track_path):
        print("[mirror_track] No track file found.", file=sys.stderr)
        sys.exit(1)

    # Resolve wheel_id
    wheel_id = args.wheel_id
    if not wheel_id:
        state_path = os.path.join(_BASE, "WAI-State.json")
        if os.path.exists(state_path):
            state = json.load(open(state_path))
            wheel_id = state.get("wheel", {}).get("wheel_id", "")

    session_id = args.session_id or os.path.basename(os.path.dirname(track_path))
    rows = track_to_activity_rows(track_path, wheel_id, session_id, args.parent_event_id)

    if args.dry_run:
        for row in rows:
            print(json.dumps(row))
        print(f"[mirror_track] {len(rows)} rows (dry run — not posted)")
        return

    # Post via emit_activity_event
    import subprocess
    ok = err = 0
    for row in rows:
        result = subprocess.run(
            ["python3", os.path.join(_HERE, "emit_activity_event.py"), json.dumps(row)],
            capture_output=True,
        )
        if result.returncode == 0:
            ok += 1
        else:
            err += 1
            print(result.stderr.decode()[:120], file=sys.stderr)

    print(f"[mirror_track] {ok} posted, {err} errors from {len(rows)} rows")


if __name__ == "__main__":
    main()
