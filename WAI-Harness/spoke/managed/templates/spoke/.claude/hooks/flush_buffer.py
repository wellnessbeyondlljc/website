"""Flush track-buffer.json to the current session's track.jsonl.

Called by stop-track-flush.sh after each Claude response.
Reads WAI-Spoke/runtime/track-buffer.json, appends to the current session's
track.jsonl, then deletes the buffer.

Usage: python3 flush_buffer.py <project_dir>
"""
import json
import os
import sys
from pathlib import Path


def main() -> None:
    project_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))

    buffer_path = project_dir / "WAI-Spoke" / "runtime" / "track-buffer.json"
    state_path = project_dir / "WAI-Spoke" / "WAI-State.json"

    if not buffer_path.exists():
        return
    if not state_path.exists():
        return

    try:
        state = json.loads(state_path.read_text())
        track_rel = state.get("_session_state", {}).get("track_path", "")
        if not track_rel:
            return

        track_path = project_dir / track_rel
        track_path.parent.mkdir(parents=True, exist_ok=True)

        entry = json.loads(buffer_path.read_text())
        with track_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

        buffer_path.unlink()
    except Exception:
        pass  # silent fail — track is best-effort


if __name__ == "__main__":
    main()
