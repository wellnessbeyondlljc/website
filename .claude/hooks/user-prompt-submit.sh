#!/bin/bash
#
# WAI UserPromptSubmit hook — harness-mode-aware (v4 + v3 fallback).
#
# Per-turn duties:
#   (1) CSRP AC4 lane heartbeat — refresh this lane's last_seen EVERY turn so a live
#       session is never TTL-reaped from the registry (which blinds every concurrency
#       guard). Initiative: csrp-intelligent-auto-reconciliation. Throttled ~5min.
#   (2) Post-compaction recovery — SessionStart does NOT fire on compaction, so inject
#       recovery context on the first user turn after a compaction.
#   (3) v3 ONLY: inject the pre-computed wakeup brief. On v4 the rich brief is owned by
#       SessionStart (wakeup-canonical.sh) — UPS must NOT re-inject it (double-inject).
#
# Base resolution: v4 first (WAI-Harness/spoke/local), v3 fallback (WAI-Spoke).

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
BASE="$PROJECT_DIR/WAI-Harness/spoke/local"; MODE="v4"
[[ -f "$BASE/WAI-State.json" ]] || { BASE="$PROJECT_DIR/WAI-Spoke"; MODE="v3"; }
STATE_FILE="$BASE/WAI-State.json"
[[ ! -f "$STATE_FILE" ]] && exit 0   # not a WAI project

RUNTIME_DIR="$BASE/runtime"
_UPS_INPUT=$(timeout 2 cat 2>/dev/null || true)
_UPS_SID=$(printf '%s' "$_UPS_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
_UPS_TRANSCRIPT=$(printf '%s' "$_UPS_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
[[ -z "$_UPS_SID" && -n "$_UPS_TRANSCRIPT" ]] && _UPS_SID=$(basename "$_UPS_TRANSCRIPT" .jsonl)

# (1) CSRP AC4 — per-turn lane heartbeat (throttled ~5min via marker; fails silent).
if [[ -n "$_UPS_SID" ]]; then
  _HBM="$BASE/runtime/lanes/$_UPS_SID/.hb"
  if [[ -z "$(find "$_HBM" -mmin -5 2>/dev/null)" ]]; then
    _WG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py"
    [[ -f "$_WG" ]] && python3 "$_WG" lane-register --session "$_UPS_SID" --base "$BASE" --transcript "$_UPS_TRANSCRIPT" >/dev/null 2>&1 || true
    mkdir -p "$(dirname "$_HBM")" 2>/dev/null && touch "$_HBM" 2>/dev/null || true
  fi
fi

# Per-lane session guard (key by CC session_id so concurrent sessions never clobber).
if [[ -n "$_UPS_SID" ]]; then
  GUARD_FILE="$RUNTIME_DIR/lanes/$_UPS_SID/guard.json"
else
  GUARD_FILE="$RUNTIME_DIR/session-guard.json"
fi
mkdir -p "$(dirname "$GUARD_FILE")"

GUARD_SESSION_ID=""; GUARD_COMPLETED="false"
if [[ -f "$GUARD_FILE" ]]; then
  GUARD_SESSION_ID=$(jq -r '.session_id // ""' "$GUARD_FILE" 2>/dev/null || echo "")
  GUARD_COMPLETED=$(jq -r '.protocol_completed // false' "$GUARD_FILE" 2>/dev/null || echo "false")
fi
LAST_SESSION_ID=$(jq -r '._session_state.last_session_id // ""' "$STATE_FILE" 2>/dev/null || echo "")
if [[ -z "$GUARD_SESSION_ID" || "$GUARD_SESSION_ID" == "$LAST_SESSION_ID" ]]; then
  printf '{"session_id":"session-%s","protocol_completed":false,"started_at":"%s"}\n' \
    "$(date +%Y%m%d-%H%M)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$GUARD_FILE"
  GUARD_COMPLETED="false"
fi

# (2) Post-compaction recovery flag (written by pre-compact.sh).
COMPACT_FLAG="$RUNTIME_DIR/compacted.flag"
POST_COMPACT=false
if [[ -f "$COMPACT_FLAG" ]]; then POST_COMPACT=true; rm -f "$COMPACT_FLAG"; fi
export POST_COMPACT

# Already ran this session and no compaction to recover → nothing more to do
# (the heartbeat above already fired, which is the per-turn essential).
[[ "$GUARD_COMPLETED" == "true" && "$POST_COMPACT" == "false" ]] && exit 0

# Mark protocol triggered (runtime file only — WAI-State.json stays clean).
TMP=$(mktemp)
jq '.protocol_completed = true | .protocol_last_run = (now | strftime("%Y-%m-%dT%H:%M:%SZ"))' "$GUARD_FILE" > "$TMP" 2>/dev/null && mv "$TMP" "$GUARD_FILE" || rm -f "$TMP"

# ── v4: brief is owned by SessionStart. Inject ONLY post-compact recovery. ──
if [[ "$MODE" == "v4" ]]; then
  if [[ "$POST_COMPACT" == "true" ]]; then
    python3 - <<'PYEOF'
import json
ctx = ("<wai-post-compact>\n"
       "Context compaction just occurred. Before responding to the user:\n"
       "1. Re-read WAI-State.json (WAI-Harness/spoke/local) to restore session context.\n"
       "2. If mid-closeout: re-read wai-closeout.md and resume from the step you were on.\n"
       "3. Check recent track entries to understand what was in progress.\n"
       "P1-Persist and P11-Lug-First are still active.\n"
       "</wai-post-compact>")
print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ctx}}))
PYEOF
  fi
  exit 0
fi

# ── v3 legacy path: inject the pre-computed wakeup brief (BASE == WAI-Spoke). ──
export PROJECT_DIR
python3 - << 'PYEOF'
import json, os, subprocess
from pathlib import Path

project_dir = Path(os.environ.get('PROJECT_DIR', '.'))
brief_file  = project_dir / 'WAI-Spoke' / 'wakeup-brief.json'
state_file  = project_dir / 'WAI-Spoke' / 'WAI-State.json'
intent_file = project_dir / 'WAI-Spoke' / 'runtime' / 'session-intent.json'
intent = intent_label = None
if intent_file.exists():
    try:
        id_data = json.loads(intent_file.read_text())
        intent = id_data.get('intent'); intent_label = id_data.get('intent_label', '')
    except Exception:
        pass

def brief_freshness(brief):
    try:
        current_sha = subprocess.check_output(['git','rev-parse','HEAD'], cwd=str(project_dir), stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return 'STALE'
    brief_sha = brief.get('git_sha_at_generation', '')
    if not brief_sha: return 'STALE'
    if current_sha == brief_sha: return 'FRESH'
    RELEVANT = ['WAI-Spoke/WAI-State.json','WAI-Spoke/lugs/bytype/','WAI-Spoke/seed/ingest/processed/','templates/commands/wai']
    try:
        changed = subprocess.check_output(['git','diff','--name-only',brief_sha,current_sha], cwd=str(project_dir), stderr=subprocess.DEVNULL).decode().strip().split('\n')
        if not any(any(r in f for r in RELEVANT) for f in changed if f): return 'FRESH'
    except Exception:
        pass
    return 'STALE'

lines = []; status = 'STALE'
if brief_file.exists():
    try:
        brief = json.loads(brief_file.read_text())
        status = brief_freshness(brief)
        if status == 'FRESH':
            try:
                state = json.loads(state_file.read_text())
                name = state.get('wheel', {}).get('name', 'Unknown')
                version = state.get('wheel', {}).get('version', '?')
                sc = state.get('_session_state', {}).get('session_count', 0)
            except Exception:
                name, version, sc = 'Unknown', '?', 0
            qs = brief.get('queue_snapshot', {}); tp = brief.get('teachings_pending', 0)
            hs = brief.get('hub_signals_pending', 0); na = ((brief.get('next_actions') or ['None'])[0])[:120]
            ol = brief.get('open_lug_count', 0)
            lines += [f'Project: {name} v{version}', f'Session: {sc + 1}', f'Active: {ol} open',
                      f'Queue: {qs.get("ready_count",0)} ready | {qs.get("needs_refinement_count",0)} refinement | {qs.get("blocked_count",0)} blocked']
            if tp > 0: lines.append(f'Teachings: {tp} pending')
            if hs > 0: lines.append(f'Hub signals: {hs}')
            lines.append(f'Next: {na}')
    except Exception:
        pass
try:
    n = len([l for l in subprocess.check_output(['git','status','--short'], cwd=str(project_dir), stderr=subprocess.DEVNULL).decode().strip().split('\n') if l])
    lines.append(f'Uncommitted: {n} files')
except Exception:
    pass
if intent: lines.append(f'Intent: {intent} — {intent_label}')
if intent == 'implement':
    directive = ('DIRECTIVE: Intent=implement. Do NOT run /wai or teaching adoption. Read WAI-Spoke/lugs/bytype/task/open/ (1 call), brief user on in-progress lug state, begin implementation.')
elif intent == 'savepoint':
    directive = 'DIRECTIVE: Intent=savepoint resume. Read WAI-State._savepoint (1 call), load named lug, resume work.'
elif intent == 'teachings':
    directive = 'DIRECTIVE: Intent=teachings. Run /wai (wai-learn is deprecated — absorbed into wai Step 3a).'
elif intent == 'closeout':
    directive = 'DIRECTIVE: Intent=closeout. Run /wai-closeout.'
elif intent == 'refinement':
    directive = 'DIRECTIVE: Intent=refinement. Skip teaching adoption. Load needs_refinement queue.'
else:
    directive = ('DIRECTIVE: Run WAI wakeup protocol (/wai skill, templates/commands/wai.md). Include pending teachings in briefing. Do not stop wakeup before briefing is complete.')
post_compact = os.environ.get('POST_COMPACT', 'false') == 'true'
pcb = []
if post_compact:
    pcb = ['', '<wai-post-compact>', 'Context compaction just occurred. Before responding to the user:',
           '1. Re-read WAI-State.json to restore session context.',
           '2. If mid-closeout: re-read wai-closeout.md and resume from the step you were on.',
           '3. Check recent track entries to understand what was in progress.',
           'P1-Persist and P11-Lug-First are still active.', '</wai-post-compact>']
content_lines = ['<wai-session-init>', f'Wakeup brief: {status}'] + lines + pcb + [
    '', directive, 'EXCEPTION: If user message is a closeout command (/wai-closeout), skip briefing.', '</wai-session-init>']
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': '\n'.join(content_lines)}}))
PYEOF
exit 0
