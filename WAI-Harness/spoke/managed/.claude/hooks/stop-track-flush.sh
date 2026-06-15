#!/bin/bash
# stop-track-flush.sh — Commit a track entry to the session track.jsonl every turn.
# Called by the Claude Code Stop hook after each response.
#
# Harness-mode-aware (v3/v4). Sources harness_mode.sh and resolves the DATA tree where
# the live per-turn ledger actually lives, then writes buffer + track + cursor + autosave
# under it: WAI-Spoke/ in v3, WAI-Harness/spoke/local/ in v4. One script, both modes.
#
# Two layers, so a turn is NEVER lost:
#   1. Rich layer  — if the model wrote <runtime>/track-buffer.json, flush it.
#   2. Safety net  — synthesize a baseline entry from the CC transcript (transcript_path
#                    on stdin) when no buffer existed this turn. A cursor file dedups.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# Resolve v3/v4 coexistence (exports HARNESS_V3/V4/MODE/ACTIVE/ROOT). v3-safe; never errors.
HM="$PROJECT_DIR/.claude/hooks/harness_mode.sh"
if [[ -f "$HM" ]]; then
  # shellcheck disable=SC1090
  source "$HM" "$PROJECT_DIR"
else
  # Degraded fallback: infer presence from on-disk dirs.
  HARNESS_V3=0; HARNESS_V4=0
  [[ -d "$PROJECT_DIR/WAI-Spoke" ]]   && HARNESS_V3=1
  [[ -d "$PROJECT_DIR/WAI-Harness" ]] && HARNESS_V4=1
fi

# Data-plane selection. The per-turn ledger follows the CANONICAL session hook, which is
# v3 whenever WAI-Spoke/ is present (coexist or v3-only) and v4 only once it is gone.
# This is deliberately NOT HARNESS_ACTIVE: HARNESS_ACTIVE tracks managed-tooling currency
# (it defaults to v4 in coexist), but in coexist the live session ledger is still v3, so
# following HARNESS_ACTIVE would write to the wrong tree every turn. An explicit
# WAI_HARNESS_MODE override still wins (used by the v4-only forced regression test).
DATA_ACTIVE=""
case "${WAI_HARNESS_MODE:-}" in
  v4) [[ "$HARNESS_V4" == 1 ]] && DATA_ACTIVE=v4 ;;
  v3) [[ "$HARNESS_V3" == 1 ]] && DATA_ACTIVE=v3 ;;
esac
if [[ -z "$DATA_ACTIVE" ]]; then
  if   [[ "$HARNESS_V3" == 1 ]]; then DATA_ACTIVE=v3
  elif [[ "$HARNESS_V4" == 1 ]]; then DATA_ACTIVE=v4
  else exit 0; fi
fi

if [[ "$DATA_ACTIVE" == v4 ]]; then
  BASE="$PROJECT_DIR/WAI-Harness/spoke/local"
else
  BASE="$PROJECT_DIR/WAI-Spoke"
fi
STATE="$BASE/WAI-State.json"
RUNTIME="$BASE/runtime"
BUFFER="$RUNTIME/track-buffer.json"

[[ -f "$STATE" ]] || exit 0

# Read Stop-hook payload from stdin (contains transcript_path + session_id); tolerate
# empty stdin. The CC session_id (== transcript basename) is this session's LANE KEY —
# it routes the turn to this session's own track + private runtime, so concurrent
# sessions never cross-write each other's ledger.
INPUT=$(cat 2>/dev/null)
TRANSCRIPT=$(printf '%s' "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
CC_SID=$(printf '%s' "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
# Fallback: derive the lane key from the transcript filename (<uuid>.jsonl).
[[ -z "$CC_SID" && -n "$TRANSCRIPT" ]] && CC_SID=$(basename "$TRANSCRIPT" .jsonl)

# Resolve this session's lane (idempotent; lazy-creates if Stop fires without a prior
# SessionStart). Yields the lane's own track + private runtime dir.
TRACK=""
LANE_DIR=""
_WG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py"
if [[ -n "$CC_SID" && -f "$_WG" ]]; then
  _LANE=$(python3 "$_WG" lane-resolve --session "$CC_SID" --base "$BASE" --transcript "$TRANSCRIPT" 2>/dev/null)
  if [[ -n "$_LANE" ]]; then
    TRACK=$(printf '%s' "$_LANE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('track_path',''))" 2>/dev/null)
    LANE_DIR=$(printf '%s' "$_LANE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('lane_dir',''))" 2>/dev/null)
  fi
fi

# Fallback (no lane / no session id): legacy routing via _session_state.track_path,
# then newest session dir. Lane dir falls back to the shared runtime.
if [[ -z "$TRACK" ]]; then
  TRACK=$(BASE="$BASE" PROJECT_DIR="$PROJECT_DIR" STATE="$STATE" python3 - <<'PYEOF' 2>/dev/null
import json, os
from pathlib import Path
base = Path(os.environ["BASE"]); proj = Path(os.environ["PROJECT_DIR"]); state = os.environ["STATE"]
track = ""
try:
    rel = json.loads(Path(state).read_text()).get("_session_state", {}).get("track_path", "")
    if rel:
        cand = proj / rel
        if cand.parent.exists() or str(cand).startswith(str(base)):
            track = str(cand)
except Exception:
    pass
if not track:
    sess = base / "sessions"
    if sess.is_dir():
        dirs = [d for d in sess.iterdir() if d.is_dir()]
        if dirs:
            newest = max(dirs, key=lambda d: d.stat().st_mtime)
            track = str(newest / "track.jsonl")
print(track)
PYEOF
)
fi
[[ -z "$TRACK" ]] && exit 0
[[ -z "$LANE_DIR" ]] && LANE_DIR="$RUNTIME"

# Buffer: prefer this lane's private buffer; fall back to the shared buffer (the
# model's default write target in single-session mode).
BUFFER="$LANE_DIR/track-buffer.json"
[[ ! -f "$BUFFER" && -f "$RUNTIME/track-buffer.json" ]] && BUFFER="$RUNTIME/track-buffer.json"

# Harness-resolved context for the Python helpers. WAI_LANE_DIR scopes cursor/guard/
# autosave to this session; WAI_RUNTIME_DIR stays shared (provider_usage telemetry).
export WAI_TRACK_PATH="$TRACK" WAI_LANE_DIR="$LANE_DIR" WAI_RUNTIME_DIR="$RUNTIME" WAI_BASE_DIR="$BASE" WAI_STATE_PATH="$STATE"

# Layer 1: flush model-authored rich entry if present.
BUFFER_PRESENT=0
if [[ -f "$BUFFER" ]]; then
  python3 "$PROJECT_DIR/.claude/hooks/flush_buffer.py" "$STATE" "$BUFFER" "$PROJECT_DIR"
  BUFFER_PRESENT=1
fi

# Layer 2: transcript-derived safety net (advances cursor; synthesizes only if no buffer).
if [[ -n "$TRANSCRIPT" ]]; then
  python3 "$PROJECT_DIR/.claude/hooks/synthesize_turn.py" \
    "$STATE" "$TRANSCRIPT" "$PROJECT_DIR" "$BUFFER_PRESENT" 2>/dev/null
fi

exit 0
