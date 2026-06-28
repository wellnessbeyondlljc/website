#!/bin/bash
#
# WAI PreCompact Hook — State Preservation
# Saves critical context before Claude compacts the conversation.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
# v4-first base (guarded v3 fallback) keyed by WAI-State.json, never a bare dir. Without
# this, a v4-only spoke read a non-existent WAI-Spoke/WAI-State.json (silent no-op) AND
# the flag write below mkdir'd a phantom WAI-Spoke/runtime — recreating the v3 husk.
BASE="$PROJECT_DIR/WAI-Harness/spoke/local"
[[ -f "$BASE/WAI-State.json" ]] || BASE="$PROJECT_DIR/WAI-Spoke"
STATE_FILE="$BASE/WAI-State.json"

# Exit silently if not a WAI project
[[ ! -f "$STATE_FILE" ]] && exit 0

TRACK_PATH=$(jq -r '._session_state.track_path // ""' "$STATE_FILE" 2>/dev/null)
TRACK_TURNS=0
if [[ -n "$TRACK_PATH" && -f "$PROJECT_DIR/$TRACK_PATH" ]]; then
  TRACK_TURNS=$(wc -l < "$PROJECT_DIR/$TRACK_PATH" 2>/dev/null || echo 0)
fi

ACTIVE_LUGS=$(ls "$BASE"/lugs/bytype/*/open/*.json "$BASE"/lugs/bytype/*/in_progress/*.json 2>/dev/null | wc -l)

cat << COMPACT
<wai-pre-compact>
Context compaction occurring. Key state preserved:
- Track: $TRACK_PATH ($TRACK_TURNS turns recorded)
- Active lugs: $ACTIVE_LUGS items across bytype/
- State: $STATE_FILE (last session: $(jq -r '._session_state.last_session_id // "unknown"' "$STATE_FILE" 2>/dev/null))
- Next actions: $(jq -r '._session_state.next_session_recommendation // "none"' "$STATE_FILE" 2>/dev/null | head -c 200)

After compaction: Re-read WAI-State.json and recent track entries to rebuild context.
Rules still active: P1-Persist, P2-Verify, P3-Steward, P10-Autonomy, P11-Lug-First.
</wai-pre-compact>
COMPACT

# Write flag so user-prompt-submit.sh re-orients the model after compaction —
# under the RESOLVED base (v4 spoke/local/runtime), never a phantom WAI-Spoke/runtime.
mkdir -p "$BASE/runtime"
printf 'true' > "$BASE/runtime/compacted.flag"

exit 0
