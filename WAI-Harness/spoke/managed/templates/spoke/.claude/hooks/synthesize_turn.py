"""Synthesize a baseline track entry from the Claude Code transcript.

Safety net for the WAI Track ledger: when the model does not write
track-buffer.json for a turn, this reconstructs a faithful turn entry directly
from the transcript so no turn is ever lost. The model-authored buffer remains
the preferred ("rich") layer; this is the guaranteed floor beneath it.

Live (Stop hook):
    synthesize_turn.py <state_path> <transcript_path> <project_dir> <buffer_was_present>
      - <buffer_was_present> "1": the Stop hook already flushed a rich entry this
        turn, so we only advance the cursor (no double-write). "0": synthesize.
      - Cursor (WAI-Spoke/runtime/track-cursor.json) stores the last transcript
        uuid accounted for, so turns are never double-written or missed.

Backfill (one-shot recovery of a whole session):
    synthesize_turn.py --all <state_path> <transcript_path> <project_dir>
      - Reconstructs every genuine turn not already present (dedup by user_uuid).

Turn boundary: a genuine user turn is a transcript entry with
promptSource == "typed". This is precise -- it ignores tool-results and
hook-injected system-reminders (validated: 8 typed prompts matched 8 real turns
exactly against a real transcript; 94 non-typed entries were all noise).

Best-effort: every failure is swallowed silently; track must never break a
session. The only way a turn is lost is a hard crash of this script itself.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _load_jsonl(path):
    rows = []
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return rows


def _is_typed_user(entry):
    """Genuine user turn boundary: type==user AND promptSource=='typed'."""
    return entry.get("type") == "user" and entry.get("promptSource") == "typed"


def _text_of(content):
    """Flatten message.content (str or list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return ""


def _resolve_contributor():
    """Resolve (contributor, kind) for attribution.

    Autonomous runs set WAI_AGENT_NAME (e.g. 'tender', 'ozi', 'autopilot').
    Interactive sessions resolve git user.name, falling back to $USER.
    Returns (contributor_slug, kind) where kind in {'user', 'agent'}.
    """
    agent_name = os.environ.get("WAI_AGENT_NAME", "").strip()
    if agent_name:
        slug = re.sub(r"[^a-z0-9-]", "", agent_name.lower().replace(" ", "-"))
        return slug or "agent", "agent"
    try:
        name = subprocess.check_output(
            ["git", "config", "user.name"], stderr=subprocess.DEVNULL
        ).decode().strip()
        slug = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
        return slug or os.environ.get("USER", "unknown"), "user"
    except Exception:
        return os.environ.get("USER", "unknown"), "user"


def _build_turn(rows, start_idx, end_idx, turn_no,
                contributor="", kind="user", origin_session_id=""):
    """Full-fidelity baseline entry for rows[start_idx:end_idx] (no truncation)."""
    user = rows[start_idx]
    user_text = _text_of(user.get("message", {}).get("content"))

    assistant_texts, tools, files = [], {}, []
    last_assistant_uuid, last_ts = "", user.get("timestamp", "")

    for entry in rows[start_idx + 1:end_idx]:
        if entry.get("type") != "assistant":
            continue
        last_assistant_uuid = entry.get("uuid", last_assistant_uuid)
        last_ts = entry.get("timestamp", last_ts)
        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for blk in content:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "text" and blk.get("text", "").strip():
                assistant_texts.append(blk["text"])
            elif blk.get("type") == "tool_use":
                name = blk.get("name", "?")
                tools[name] = tools.get(name, 0) + 1
                inp = blk.get("input", {})
                if isinstance(inp, dict):
                    fp = inp.get("file_path") or inp.get("path")
                    if fp and fp not in files:
                        files.append(fp)

    return {
        "event": "turn",
        "turn": turn_no,
        "source": "transcript-synth",
        "synthesized": True,
        "session_id": user.get("sessionId", ""),
        "origin_session_id": origin_session_id or user.get("sessionId", ""),
        "contributor": contributor,
        "kind": kind,
        "user_uuid": user.get("uuid", ""),
        "assistant_uuid": last_assistant_uuid,
        "user_ts": user.get("timestamp", ""),
        "ts": last_ts,
        "git_branch": user.get("gitBranch", ""),
        "user_intent": user_text,
        "assistant_text": "\n\n".join(assistant_texts),
        "tools_used": [{"name": k, "count": v} for k, v in tools.items()],
        "files_touched": files,
    }


def _track_path(state_path, project_dir):
    state = json.loads(Path(state_path).read_text())
    rel = state.get("_session_state", {}).get("track_path", "")
    if not rel:
        return None
    p = Path(project_dir) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _current_session_id(state_path):
    """Read the current session_id from WAI-State or the session guard."""
    try:
        state = json.loads(Path(state_path).read_text())
        return state.get("_session_state", {}).get("last_session_id", "")
    except Exception:
        return ""


def _existing_turn_count(track_path):
    return sum(1 for r in _load_jsonl(track_path) if r.get("event") == "turn")


def _session_closed(track_path, current_session_id=""):
    """True if the track's terminal closeout belongs to the CURRENT session.

    Per-session scoped so multi-session tracks are safe: one contributor
    closing out does not strand another session's appends. If no session_id
    context is available, falls back to a whole-file check.
    """
    rows = _load_jsonl(track_path)
    if not rows:
        return False
    last = rows[-1]
    if last.get("event") != "closeout":
        return False
    if current_session_id:
        # Only treat as closed if the closeout belongs to THIS session.
        closeout_session = last.get("session_id") or last.get("origin_session_id", "")
        return closeout_session == current_session_id
    # No session context: whole-file fallback (safe for single-session tracks).
    return True


def _has_meaning(entry):
    return bool(entry["user_intent"] or entry["assistant_text"] or entry["tools_used"])


def backfill(state_path, transcript_path, project_dir):
    """Reconstruct every genuine turn not already recorded (dedup by user_uuid)."""
    track = _track_path(state_path, project_dir)
    if track is None:
        return
    rows = _load_jsonl(transcript_path)
    if not rows:
        return
    starts = [i for i, e in enumerate(rows) if _is_typed_user(e)]
    if not starts:
        return
    bounds = starts + [len(rows)]
    seen = {r.get("user_uuid") for r in _load_jsonl(track) if r.get("user_uuid")}
    turn_no = _existing_turn_count(track)
    contributor, kind = _resolve_contributor()
    session_id = _current_session_id(state_path)
    out = []
    for ci, si in enumerate(starts):
        if rows[si].get("uuid") in seen:
            continue
        turn_no += 1
        out.append(_build_turn(rows, bounds[ci], bounds[ci + 1], turn_no,
                               contributor=contributor, kind=kind,
                               origin_session_id=session_id))
    out = [e for e in out if _has_meaning(e)]
    if out:
        with track.open("a") as f:
            for e in out:
                f.write(json.dumps(e) + "\n")


def live(state_path, transcript_path, project_dir, buffer_was_present):
    """Synthesize the just-completed turn (unless a rich buffer was flushed)."""
    track = _track_path(state_path, project_dir)
    if track is None:
        return
    session_id = _current_session_id(state_path)
    # Session is closing -- do not append turns after the terminal closeout entry.
    if _session_closed(track, current_session_id=session_id):
        return
    rows = _load_jsonl(transcript_path)
    if not rows:
        return

    cursor_path = Path(project_dir) / "WAI-Spoke" / "runtime" / "track-cursor.json"
    last_uuid = ""
    try:
        last_uuid = json.loads(cursor_path.read_text()).get("last_uuid", "")
    except Exception:
        last_uuid = ""

    # Window = entries after the cursor. If cursor is unknown/stale, anchor to the
    # last typed prompt so we never backfill the whole transcript on first run.
    start_idx = 0
    if last_uuid:
        for i, e in enumerate(rows):
            if e.get("uuid") == last_uuid:
                start_idx = i + 1
                break
    if not last_uuid or start_idx == 0:
        typed = [i for i, e in enumerate(rows) if _is_typed_user(e)]
        start_idx = typed[-1] if typed else 0

    window = rows[start_idx:]
    if not window:
        return

    # Always advance the cursor so the next turn picks up cleanly.
    newest_uuid = next((e["uuid"] for e in reversed(window) if e.get("uuid")), "")
    try:
        cursor_path.parent.mkdir(parents=True, exist_ok=True)
        cursor_path.write_text(json.dumps({"last_uuid": newest_uuid}))
    except Exception:
        pass

    # Rich entry already written by the model this turn -- cursor advanced, done.
    if buffer_was_present:
        return

    contributor, kind = _resolve_contributor()

    # Boundary inside the window: last typed prompt -> end is "this turn".
    typed_in_window = [i for i, e in enumerate(window) if _is_typed_user(e)]
    if not typed_in_window:
        return
    s = typed_in_window[-1]
    entry = _build_turn(window, s, len(window), _existing_turn_count(track) + 1,
                        contributor=contributor, kind=kind, origin_session_id=session_id)
    if not _has_meaning(entry):
        return
    with track.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    args = sys.argv[1:]
    if not args:
        return
    try:
        if args[0] == "--all":
            if len(args) >= 4:
                backfill(args[1], args[2], args[3])
            return
        if len(args) >= 4:
            live(args[0], args[1], args[2], args[3] == "1")
    except Exception:
        pass  # track is best-effort; never break the session


if __name__ == "__main__":
    main()
