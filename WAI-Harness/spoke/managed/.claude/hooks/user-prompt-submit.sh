#!/bin/bash
#
# WAI Session Hook — injects pre-computed wakeup brief for fast path
# Runs BEFORE Claude sees the user's message on first turn.
# Injects <wai-session-init> with brief data so /wai fast path fires without tool calls.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
STATE_FILE="$PROJECT_DIR/WAI-Spoke/WAI-State.json"

# Exit silently if not a WAI project
[[ ! -f "$STATE_FILE" ]] && exit 0

# Session guard uses a runtime file (gitignored) to avoid dirtying WAI-State.json.
# Per-lane: key the guard by the CC session_id (from this hook's stdin payload) so two
# concurrent sessions never overwrite each other's guard. No session_id (older CC) →
# the legacy shared guard path, unchanged.
RUNTIME_DIR="$PROJECT_DIR/WAI-Spoke/runtime"
_UPS_INPUT=$(timeout 2 cat 2>/dev/null || true)
_UPS_SID=$(printf '%s' "$_UPS_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
_UPS_TRANSCRIPT=$(printf '%s' "$_UPS_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
[[ -z "$_UPS_SID" && -n "$_UPS_TRANSCRIPT" ]] && _UPS_SID=$(basename "$_UPS_TRANSCRIPT" .jsonl)
if [[ -n "$_UPS_SID" ]]; then
  GUARD_FILE="$RUNTIME_DIR/lanes/$_UPS_SID/guard.json"
else
  GUARD_FILE="$RUNTIME_DIR/session-guard.json"
fi
mkdir -p "$(dirname "$GUARD_FILE")"

# Read guard state (if exists)
GUARD_SESSION_ID=""
GUARD_COMPLETED="false"
if [[ -f "$GUARD_FILE" ]]; then
  GUARD_SESSION_ID=$(jq -r '.session_id // ""' "$GUARD_FILE" 2>/dev/null || echo "")
  GUARD_COMPLETED=$(jq -r '.protocol_completed // false' "$GUARD_FILE" 2>/dev/null || echo "false")
fi

# Detect new session: compare guard's session_id vs state's last_session_id
LAST_SESSION_ID=$(jq -r '._session_state.last_session_id // ""' "$STATE_FILE" 2>/dev/null || echo "")

# New session if guard is empty or matches the last committed session
if [[ -z "$GUARD_SESSION_ID" || "$GUARD_SESSION_ID" == "$LAST_SESSION_ID" ]]; then
  # Generate a fresh session ID for this session
  NEW_SESSION_ID="session-$(date +%Y%m%d-%H%M)"
  printf '{"session_id":"%s","protocol_completed":false,"started_at":"%s"}\n' \
    "$NEW_SESSION_ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$GUARD_FILE"
  GUARD_COMPLETED="false"
fi

# Check for post-compaction recovery (flag written by pre-compact.sh)
COMPACT_FLAG="$RUNTIME_DIR/compacted.flag"
POST_COMPACT=false
if [[ -f "$COMPACT_FLAG" ]]; then
  POST_COMPACT=true
  rm -f "$COMPACT_FLAG"
fi
export POST_COMPACT

# Skip if protocol already ran this session (unless post-compact recovery needed)
[[ "$GUARD_COMPLETED" == "true" && "$POST_COMPACT" == "false" ]] && exit 0

# Mark protocol as triggered (in runtime file only — WAI-State.json stays clean)
TMP=$(mktemp)
jq '.protocol_completed = true |
    .protocol_last_run = (now | strftime("%Y-%m-%dT%H:%M:%SZ"))' "$GUARD_FILE" > "$TMP" && mv "$TMP" "$GUARD_FILE"

# Inject <wai-session-init> with pre-computed brief data (enables fast path in /wai)
export PROJECT_DIR
python3 - << 'PYEOF'
import json, os, subprocess
from pathlib import Path

project_dir = Path(os.environ.get('PROJECT_DIR', '.'))
brief_file  = project_dir / 'WAI-Spoke' / 'wakeup-brief.json'
state_file  = project_dir / 'WAI-Spoke' / 'WAI-State.json'

# Intent file reading (unconditional — works even when brief is stale)
intent_file = project_dir / 'WAI-Spoke' / 'runtime' / 'session-intent.json'
intent = None
intent_label = None
if intent_file.exists():
    try:
        id_data = json.loads(intent_file.read_text())
        intent = id_data.get('intent')
        intent_label = id_data.get('intent_label', '')
    except Exception:
        pass

def brief_freshness(brief):
    """Returns 'FRESH' if brief SHA matches HEAD (smart: irrelevant commits don't stale)."""
    try:
        current_sha = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=str(project_dir),
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return 'STALE'
    brief_sha = brief.get('git_sha_at_generation', '')
    if not brief_sha:
        return 'STALE'
    if current_sha == brief_sha:
        return 'FRESH'
    # Smart staleness: only stale if relevant files changed
    RELEVANT = ['WAI-Spoke/WAI-State.json', 'WAI-Spoke/lugs/bytype/',
                'WAI-Spoke/seed/ingest/processed/', 'templates/commands/wai']
    try:
        changed = subprocess.check_output(
            ['git', 'diff', '--name-only', brief_sha, current_sha],
            cwd=str(project_dir), stderr=subprocess.DEVNULL).decode().strip().split('\n')
        if not any(any(r in f for r in RELEVANT) for f in changed if f):
            return 'FRESH'
    except Exception:
        pass
    return 'STALE'

lines = []
status = 'STALE'

if brief_file.exists():
    try:
        brief = json.loads(brief_file.read_text())
        status = brief_freshness(brief)
        if status == 'FRESH':
            try:
                state   = json.loads(state_file.read_text())
                name    = state.get('wheel', {}).get('name', 'Unknown')
                version = state.get('wheel', {}).get('version', '?')
                sc      = state.get('_session_state', {}).get('session_count', 0)
            except Exception:
                name, version, sc = 'Unknown', '?', 0
            qs = brief.get('queue_snapshot', {})
            tp = brief.get('teachings_pending', 0)
            hs = brief.get('hub_signals_pending', 0)
            na = ((brief.get('next_actions') or ['None'])[0])[:120]
            ol = brief.get('open_lug_count', 0)
            lines += [
                f'Project: {name} v{version}',
                f'Session: {sc + 1}',
                f'Active: {ol} open',
                f'Queue: {qs.get("ready_count",0)} ready | {qs.get("needs_refinement_count",0)} refinement | {qs.get("blocked_count",0)} blocked',
            ]
            if tp > 0: lines.append(f'Teachings: {tp} pending')
            if hs > 0: lines.append(f'Hub signals: {hs}')
            lines.append(f'Next: {na}')
    except Exception:
        pass

# Git health line
try:
    n = len([l for l in subprocess.check_output(
        ['git', 'status', '--short'], cwd=str(project_dir),
        stderr=subprocess.DEVNULL).decode().strip().split('\n') if l])
    lines.append(f'Uncommitted: {n} files')
except Exception:
    pass

# Intent-conditional directive
if intent:
    lines.append(f'Intent: {intent} — {intent_label}')

if intent == 'implement':
    directive = ('DIRECTIVE: Intent=implement. Do NOT run /wai or teaching adoption. '
                 'Read WAI-Spoke/lugs/bytype/task/open/ (1 call), brief user on in-progress lug state, begin implementation.')
elif intent == 'savepoint':
    directive = 'DIRECTIVE: Intent=savepoint resume. Read WAI-State._savepoint (1 call), load named lug, resume work.'
elif intent == 'teachings':
    directive = 'DIRECTIVE: Intent=teachings. Run /wai (wai-learn is deprecated — absorbed into wai Step 3a).'
elif intent == 'closeout':
    directive = 'DIRECTIVE: Intent=closeout. Run /wai-closeout.'
elif intent == 'refinement':
    directive = 'DIRECTIVE: Intent=refinement. Skip teaching adoption. Load needs_refinement queue.'
else:
    directive = ('DIRECTIVE: Run WAI wakeup protocol (/wai skill, templates/commands/wai.md). '
                 'Include pending teachings in briefing. Do not stop wakeup before briefing is complete.')

post_compact = os.environ.get('POST_COMPACT', 'false') == 'true'
post_compact_block = []
if post_compact:
    post_compact_block = [
        '',
        '<wai-post-compact>',
        'Context compaction just occurred. Before responding to the user:',
        '1. Re-read WAI-State.json to restore session context.',
        '2. If mid-closeout: re-read wai-closeout.md and resume from the step you were on.',
        '3. Check recent track entries to understand what was in progress.',
        'P1-Persist and P11-Lug-First are still active.',
        '</wai-post-compact>',
    ]

content_lines = ['<wai-session-init>', f'Wakeup brief: {status}'] + lines + post_compact_block + [
    '',
    directive,
    'EXCEPTION: If user message is a closeout command (/wai-closeout), skip briefing.',
    '</wai-session-init>',
]
import json as _json
print(_json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': '\n'.join(content_lines)}}))
PYEOF

exit 0
