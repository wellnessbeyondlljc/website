#!/bin/bash
#
# WAI PreCompact Hook — State Preservation
# Saves critical context before Claude compacts the conversation.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
STATE_FILE="$PROJECT_DIR/WAI-Spoke/WAI-State.json"

# Exit silently if not a WAI project
[[ ! -f "$STATE_FILE" ]] && exit 0

TRACK_PATH=$(jq -r '._session_state.track_path // ""' "$STATE_FILE" 2>/dev/null)
TRACK_TURNS=0
if [[ -n "$TRACK_PATH" && -f "$PROJECT_DIR/$TRACK_PATH" ]]; then
  TRACK_TURNS=$(wc -l < "$PROJECT_DIR/$TRACK_PATH" 2>/dev/null || echo 0)
fi

ACTIVE_LUGS=$(ls "$PROJECT_DIR"/WAI-Spoke/lugs/bytype/*/open/*.json "$PROJECT_DIR"/WAI-Spoke/lugs/bytype/*/in_progress/*.json 2>/dev/null | wc -l)

LAST_SESSION=$(jq -r '._session_state.last_session_id // "unknown"' "$STATE_FILE" 2>/dev/null)
NEXT_ACTIONS=$(jq -r '._session_state.next_session_recommendation // "none"' "$STATE_FILE" 2>/dev/null | head -c 200)

python3 -c "
import json, sys
track_path = sys.argv[1]
track_turns = sys.argv[2]
active_lugs = sys.argv[3]
last_session = sys.argv[4]
next_actions = sys.argv[5]
content = (
    '<wai-pre-compact>\n'
    'Context compaction occurring. Key state preserved:\n'
    '- Track: ' + track_path + ' (' + track_turns + ' turns recorded)\n'
    '- Active lugs: ' + active_lugs + ' items across bytype/\n'
    '- State: WAI-Spoke/WAI-State.json (last session: ' + last_session + ')\n'
    '- Next actions: ' + next_actions + '\n'
    '\n'
    'After compaction: Re-read WAI-State.json and recent track entries to rebuild context.\n'
    'Rules still active: P1-Persist, P2-Verify, P3-Steward, P10-Autonomy, P11-Lug-First.\n'
    '</wai-pre-compact>'
)
print(json.dumps({'hookSpecificOutput': content}))
" "$TRACK_PATH" "$TRACK_TURNS" "$ACTIVE_LUGS" "$LAST_SESSION" "$NEXT_ACTIONS"

# Write flag so user-prompt-submit.sh re-orients the model after compaction
mkdir -p "$PROJECT_DIR/WAI-Spoke/runtime"
printf 'true' > "$PROJECT_DIR/WAI-Spoke/runtime/compacted.flag"

exit 0
