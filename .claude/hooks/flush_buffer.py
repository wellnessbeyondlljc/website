"""Flush track-buffer.json to the current session's track.jsonl.

Harness-mode-aware: the calling Stop hook (stop-track-flush.sh) resolves the active
v3/v4 data tree via harness_mode.sh and exports WAI_TRACK_PATH — the absolute resolved
track.jsonl under that tree (WAI-Spoke/ in v3, WAI-Harness/spoke/local/ in v4). We honor
it. If unset (direct invocation), we fall back to the legacy v3 computation from
_session_state.track_path so the script still works standalone.

Usage: python3 flush_buffer.py <state_path> <buffer_path> <project_dir>
"""
import json
import os
import sys
from pathlib import Path


def _resolve_track(state_path, project_dir):
    """Harness-resolved track path (env) wins; else legacy v3 from state."""
    env = os.environ.get("WAI_TRACK_PATH", "")
    if env:
        return Path(env)
    try:
        state = json.loads(Path(state_path).read_text())
        rel = state.get("_session_state", {}).get("track_path", "")
        if rel:
            return Path(project_dir) / rel
    except Exception:
        pass
    return None


def main() -> None:
    if len(sys.argv) < 4:
        return

    state_path, buffer_path, project_dir = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        track_path = _resolve_track(state_path, project_dir)
        if track_path is None:
            return

        track_path.parent.mkdir(parents=True, exist_ok=True)

        entry = json.loads(Path(buffer_path).read_text())
        with track_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

        Path(buffer_path).unlink()
    except Exception:
        pass  # silent fail — track is best-effort


if __name__ == "__main__":
    main()
