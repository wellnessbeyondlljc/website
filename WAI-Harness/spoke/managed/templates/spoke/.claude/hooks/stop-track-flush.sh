#!/bin/bash
# stop-track-flush.sh -- Commit a track entry to the session track.jsonl every turn.
# Called by Claude Code Stop hook after each response.
#
# Two layers, so a turn is NEVER lost:
#   1. Rich layer  -- if the model wrote WAI-Spoke/runtime/track-buffer.json, flush it.
#   2. Safety net  -- synthesize a baseline entry from the CC transcript (transcript_path
#                    on stdin) when no buffer existed this turn. A cursor file dedups.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
BUFFER="$PROJECT_DIR/WAI-Spoke/runtime/track-buffer.json"
STATE="$PROJECT_DIR/WAI-Spoke/WAI-State.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[[ -f "$STATE" ]] || exit 0

# Read Stop-hook payload from stdin (contains transcript_path); tolerate empty stdin.
INPUT=$(cat 2>/dev/null)
TRANSCRIPT=$(printf '%s' "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)

# Layer 1: flush model-authored rich entry if present.
BUFFER_PRESENT=0
if [[ -f "$BUFFER" ]]; then
  python3 "$SCRIPT_DIR/flush_buffer.py" "$PROJECT_DIR"
  BUFFER_PRESENT=1
fi

# Layer 2: transcript-derived safety net (advances cursor; synthesizes only if no buffer).
if [[ -n "$TRANSCRIPT" ]]; then
  python3 "$SCRIPT_DIR/synthesize_turn.py" \
    "$STATE" "$TRANSCRIPT" "$PROJECT_DIR" "$BUFFER_PRESENT" 2>/dev/null
fi

exit 0
