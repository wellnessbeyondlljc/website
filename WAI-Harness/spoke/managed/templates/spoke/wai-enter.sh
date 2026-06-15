#!/bin/bash
#
# wai-enter.sh — WAI pre-tool launch wrapper (hub-aware)
#
# Auto-detects hub vs spoke and runs appropriate prep steps.
# Hub detection: WAI-Hub/ directory present
# Spoke detection: WAI-Spoke/WAI-State.json present
#
# Usage:
#   ./wai-enter.sh           # launches claude (default)
#   ./wai-enter.sh gemini    # launches gemini
#   ./wai-enter.sh codex     # launches codex
#

PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

# ── Detect project type ──────────────────────────────────────────────────────
IS_HUB=false
IS_SPOKE=false
[[ -d "$PROJECT_DIR/WAI-Hub" ]] && IS_HUB=true
[[ -f "$PROJECT_DIR/WAI-Spoke/WAI-State.json" ]] && IS_SPOKE=true

# Not a WAI project? Launch tool directly
if [[ "$IS_HUB" == "false" && "$IS_SPOKE" == "false" ]]; then
    exec "${1:-claude}" "${@:2}"
fi

echo "[wai-enter] Preparing session..."
[[ "$IS_HUB" == "true" ]] && echo "[wai-enter] Mode: hub"

# ── 1. Generate fresh wakeup brief ──────────────────────────────────────────
if [[ "$IS_HUB" == "true" && -f "$PROJECT_DIR/tools/octo_brief.py" ]]; then
    if python3 "$PROJECT_DIR/tools/octo_brief.py" 2>/dev/null; then
        echo "[wai-enter] Brief: ready (octo)"
    else
        echo "[wai-enter] Brief: octo generation failed — wakeup will use live scan"
    fi
elif [[ -f "$PROJECT_DIR/tools/generate_wakeup_brief.py" ]]; then
    if python3 "$PROJECT_DIR/tools/generate_wakeup_brief.py"; then
        echo "[wai-enter] Brief: ready"
    else
        echo "[wai-enter] Brief: generation failed — wakeup will use live scan"
    fi
else
    echo "[wai-enter] Brief: generator not found — wakeup will use live scan"
fi

# ── 1b. Intent probe (spoke only) ───────────────────────────────────────────
if [[ "$IS_SPOKE" == "true" ]]; then
    _INTENT_FILE="$PROJECT_DIR/WAI-Spoke/runtime/session-intent.json"
    _BRIEF_FILE="$PROJECT_DIR/WAI-Spoke/wakeup-brief.json"

    _READY=0; _REFINE=0; _TEACH=0; _SESSION_ID="unknown"
    if [[ -f "$_BRIEF_FILE" ]]; then
        _COUNTS=$(python3 -c "
import json
try:
    b = json.load(open('$_BRIEF_FILE'))
    qs = b.get('queue_snapshot', {})
    print(qs.get('ready_count', 0))
    print(qs.get('needs_refinement_count', 0))
    print(b.get('teachings_pending', 0))
    print(b.get('session_id', 'unknown'))
except:
    print(0); print(0); print(0); print('unknown')
" 2>/dev/null) || _COUNTS=""
        _READY=$(echo "$_COUNTS" | sed -n '1p')
        _REFINE=$(echo "$_COUNTS" | sed -n '2p')
        _TEACH=$(echo "$_COUNTS" | sed -n '3p')
        _SESSION_ID=$(echo "$_COUNTS" | sed -n '4p')
    fi
    _SIG_COUNT=$(find "$PROJECT_DIR/WAI-Spoke/lugs/bytype/signal/undelivered" -name "*.json" 2>/dev/null | wc -l || echo 0)
    _TEACH_SIG=$(( _TEACH + _SIG_COUNT ))

    _SAVEPOINT_PENDING=false; _SAVEPOINT_LUG=""; _SAVEPOINT_NOTE=""
    if [[ -f "$PROJECT_DIR/WAI-Spoke/WAI-State.json" ]]; then
        _SP=$(python3 -c "
import json
try:
    s = json.load(open('$PROJECT_DIR/WAI-Spoke/WAI-State.json'))
    sp = s.get('_savepoint', {})
    if sp.get('status') == 'pending':
        print('true')
        print(sp.get('lug_id', ''))
        print(sp.get('resume_note', '')[:60])
    else:
        print('false'); print(''); print('')
except:
    print('false'); print(''); print('')
" 2>/dev/null) || _SP=""
        _SAVEPOINT_PENDING=$(echo "$_SP" | sed -n '1p')
        _SAVEPOINT_LUG=$(echo "$_SP" | sed -n '2p')
        _SAVEPOINT_NOTE=$(echo "$_SP" | sed -n '3p')
    fi

    if [[ "$_SAVEPOINT_PENDING" == "true" && -n "$_SAVEPOINT_LUG" ]]; then
        if [[ -n "$_SAVEPOINT_NOTE" ]]; then
            _DEFAULT_LABEL="Continue savepoint: ${_SAVEPOINT_LUG} (\"${_SAVEPOINT_NOTE}\")"
        else
            _DEFAULT_LABEL="Continue savepoint: ${_SAVEPOINT_LUG}"
        fi
        _DEFAULT_INTENT="savepoint"
    else
        _DEFAULT_LABEL="Continue from last session (${_SESSION_ID})"
        _DEFAULT_INTENT="implement"
    fi

    # ── 0. Interrupted session recovery check ────────────────────────────────
    PROJECT_DIR_ENTER="$PROJECT_DIR"
    SESSIONS_DIR_ENTER="$PROJECT_DIR/WAI-Spoke/sessions"
    LUGS_DIR_ENTER="$PROJECT_DIR/WAI-Spoke/lugs/bytype"
    CUTOFF_ENTER=$(date -d '7 days ago' +%s 2>/dev/null || echo 0)

    _RECOVERY_OUTPUT=$(PROJECT_DIR="$PROJECT_DIR_ENTER" \
      SESSIONS_DIR="$SESSIONS_DIR_ENTER" \
      LUGS_DIR="$LUGS_DIR_ENTER" \
      CUTOFF="$CUTOFF_ENTER" \
    python3 - <<'PYEOF'
import sys, os, json, glob, subprocess, textwrap

project_dir  = os.environ['PROJECT_DIR']
sessions_dir = os.environ['SESSIONS_DIR']
lugs_dir     = os.environ['LUGS_DIR']
cutoff       = int(os.environ.get('CUTOFF', 0))

session_dirs = sorted(
    [d for d in glob.glob(os.path.join(sessions_dir, 'session-*'))
     if os.path.getmtime(d) >= cutoff],
    key=os.path.getmtime, reverse=True
)[:5]

interrupted = []
for sd in session_dirs:
    track = os.path.join(sd, 'track.jsonl')
    if not os.path.isfile(track) or os.path.getsize(track) == 0:
        continue
    try:
        lines = [l.strip() for l in open(track) if l.strip()]
        if not lines:
            continue
        last = json.loads(lines[-1])
        if last.get('completed') or last.get('event') == 'closeout':
            continue
        last_action = None
        for line in reversed(lines):
            try:
                ev = json.loads(line)
                if ev.get('event') == 'session_start':
                    continue
                summary = ev.get('summary') or ev.get('action') or ev.get('event', '')
                if summary:
                    last_action = str(summary)
                    break
            except Exception:
                pass
        if last_action:  # skip sessions where nothing meaningful was done
            interrupted.append({
                'session_id': os.path.basename(sd),
                'last_action': last_action,
            })
    except Exception:
        pass

if not interrupted:
    sys.exit(0)

ip_lugs = []
try:
    for f in glob.glob(os.path.join(lugs_dir, '*/in_progress/*.json')):
        try:
            d = json.load(open(f))
            lug_id = d.get('i') or os.path.splitext(os.path.basename(f))[0]
            title  = d.get('t') or d.get('title') or lug_id
            ip_lugs.append(f"{lug_id} — {title}")
        except Exception:
            pass
except Exception:
    pass

EXCLUDE = {'WAI-Spoke/WAI-State.json', 'WAI-Spoke/wakeup-brief.json', 'WAI-Spoke/ozi-brief.json'}
EXCLUDE_PREFIXES = ('WAI-Spoke/advisors/', 'WAI-Spoke/runtime/')
code_files = []
try:
    r = subprocess.run(['git', 'diff', '--name-only', 'HEAD'],
                       cwd=project_dir, capture_output=True, text=True, timeout=5)
    for f in r.stdout.strip().splitlines():
        if f not in EXCLUDE and not any(f.startswith(p) for p in EXCLUDE_PREFIXES):
            code_files.append(f)
except Exception:
    pass

W = 58
for item in interrupted:
    print(f"\n{'─'*W}")
    print(f"⚠  Interrupted work — {item['session_id']}")
    print()
    print(f"  Last action : {item['last_action'][:62]}")
    if ip_lugs:
        print(f"  In-progress : {ip_lugs[0][:58]}")
        for lug in ip_lugs[1:3]:
            print(f"              : {lug[:58]}")
    if code_files:
        extra = f" (+{len(code_files)-1} more)" if len(code_files) > 1 else ""
        print(f"  Code changes: {code_files[0]}{extra}")
    lug_str   = ip_lugs[0].split(' — ')[0] if ip_lugs else 'none'
    files_str = f"{len(code_files)} uncommitted file(s)" if code_files else "no uncommitted files"
    prompt = (f"Resume interrupted session {item['session_id']}. "
              f"Last action: {item['last_action'][:80]}. "
              f"In-progress: {lug_str}. "
              f"{files_str} — verify changes are complete before continuing.")
    print(f"\n  ── Paste to resume {'─'*(W-20)}")
    for chunk in textwrap.wrap(prompt, W-2):
        print(f"  {chunk}")
    print(f"  {'─'*W}")
print(f"{'─'*W}\n")
PYEOF
    )

    if [[ -n "$_RECOVERY_OUTPUT" ]]; then
        echo "$_RECOVERY_OUTPUT"
    fi

    echo ""
    echo "[wai-enter] What do you want to work on?"
    echo "  [Enter]  ${_DEFAULT_LABEL}"
    echo "  [1] Teachings & Signals (${_TEACH_SIG} combined)"
    echo "  [2] Refinement (${_REFINE} need refinement)"
    echo "  [3] Implement (${_READY} ready)"
    echo "  [4] Explore"
    echo "  [5] Closeout"
    echo "  [6] Full wakeup"
    echo ""
    read -r -t 30 -p "> " _INTENT_CHOICE || _INTENT_CHOICE=""

    case "$_INTENT_CHOICE" in
        "")   _INTENT="$_DEFAULT_INTENT"; _INTENT_LABEL="$_DEFAULT_LABEL" ;;
        "1")  _INTENT="teachings";   _INTENT_LABEL="Teachings & Signals (${_TEACH_SIG} combined)" ;;
        "2")  _INTENT="refinement";  _INTENT_LABEL="Refinement (${_REFINE} need refinement)" ;;
        "3")  _INTENT="implement";   _INTENT_LABEL="Implement (${_READY} ready)" ;;
        "4")  _INTENT="explore";     _INTENT_LABEL="Explore" ;;
        "5")  _INTENT="closeout";    _INTENT_LABEL="Closeout" ;;
        "6")  _INTENT="full";        _INTENT_LABEL="Full wakeup" ;;
        *)    _INTENT="$_DEFAULT_INTENT"; _INTENT_LABEL="$_DEFAULT_LABEL" ;;
    esac

    mkdir -p "$PROJECT_DIR/WAI-Spoke/runtime"
    INTENT_DATA="$_INTENT" INTENT_LABEL_DATA="$_INTENT_LABEL" SESSION_HINT="$_SESSION_ID" \
    SP_PENDING="$_SAVEPOINT_PENDING" RAW_CHOICE="$_INTENT_CHOICE" \
    python3 -c "
import json, datetime, os
entry = {
    'intent': os.environ['INTENT_DATA'],
    'intent_label': os.environ['INTENT_LABEL_DATA'],
    'selected_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'session_id_hint': os.environ['SESSION_HINT'],
    'savepoint_resumed': os.environ['SP_PENDING'] == 'true' and os.environ['INTENT_DATA'] == 'savepoint',
    'raw_choice': os.environ['RAW_CHOICE']
}
with open('$_INTENT_FILE', 'w') as f:
    f.write(json.dumps(entry, indent=2) + chr(10))
" 2>/dev/null || true
    echo "[wai-enter] Intent: ${_INTENT}"
fi

# ── 2. Refresh stale context feeds in background ────────────────────────────
if [[ "$IS_HUB" == "true" && -f "$PROJECT_DIR/tools/hub_context_refresh.py" ]]; then
    mkdir -p "$HOME/.claude/logs"
    python3 "$PROJECT_DIR/tools/hub_context_refresh.py" \
        --quiet \
        >> "$HOME/.claude/logs/hub-context-refresh-$(date +%Y%m%d).log" 2>&1 &
    echo "[wai-enter] Feeds: hub refresh running in background"
else
    EXPEDITER_STATE="$PROJECT_DIR/WAI-Spoke/advisors/expediter/scan_state.json"
    if [[ -f "$EXPEDITER_STATE" && -f "$PROJECT_DIR/tools/advisor_context_refresh.py" ]]; then
        LAST_RUN=$(python3 -c "
import json
try:
    s = json.load(open('$EXPEDITER_STATE'))
    print(s.get('last_run_at','')[:10])
except:
    print('')
" 2>/dev/null || echo "")
        TODAY=$(date +%Y-%m-%d)
        if [[ -n "$LAST_RUN" && "$LAST_RUN" != "$TODAY" ]]; then
            mkdir -p "$HOME/.claude/logs"
            python3 "$PROJECT_DIR/tools/advisor_context_refresh.py" \
                --quiet --spoke-path "$PROJECT_DIR" \
                >> "$HOME/.claude/logs/context-refresh-$(date +%Y%m%d).log" 2>&1 &
            echo "[wai-enter] Feeds: refreshing in background (last: $LAST_RUN)"
        fi
    fi
fi

# ── 3. Hub: check outbox for pending deliveries ──────────────────────────────
if [[ "$IS_HUB" == "true" ]]; then
    OUTBOX="$PROJECT_DIR/WAI-Hub/outbox"
    if [[ -d "$OUTBOX" ]]; then
        PENDING=$(find "$OUTBOX" -mindepth 2 -maxdepth 2 -name "*.json" 2>/dev/null | wc -l)
        [[ "$PENDING" -gt 0 ]] && echo "[wai-enter] Outbox: $PENDING pending deliveries"
    fi
fi

# ── 3. Spoke: run basher doctor audit if available ───────────────────────────
if [[ "$IS_HUB" == "false" ]] && command -v basher >/dev/null 2>&1; then
    BASHER_OUT=$(basher doctor audit 2>&1) || true
    BASHER_EXIT=$?
    if [[ $BASHER_EXIT -ne 0 ]] || echo "$BASHER_OUT" | grep -qiE 'fixed|changed|updated|repaired'; then
        mkdir -p "$PROJECT_DIR/WAI-Spoke/runtime"
        python3 -c "
import json, datetime
result = {
    'run_at': datetime.datetime.now().isoformat(),
    'output': '''$BASHER_OUT'''[:500],
    'exit_code': $BASHER_EXIT,
    'changes_detected': True
}
with open('$PROJECT_DIR/WAI-Spoke/runtime/basher-audit-result.json', 'w') as f:
    json.dump(result, f, indent=2)
" 2>/dev/null || true
        echo "[wai-enter] Basher: config changes detected — see wakeup blurb"
    else
        echo "[wai-enter] Basher: OK"
    fi
fi

# ── 4. Spoke: detect anomalies outside WAI-Spoke/ (read-only) ───────────────
if [[ "$IS_HUB" == "false" ]]; then
    ANOMALIES=0

    for d in "$PROJECT_DIR"/session-*/; do
        [[ -d "$d" ]] || continue
        NAME=$(basename "$d")
        TS=$(date +%s)
        python3 -c "
import json, datetime
lug = {
    'id': 'signal-pre-wrapper-anomaly-${TS}-v1',
    'type': 'signal',
    'status': 'undelivered',
    'title': 'Anomaly: session dir at project root: $NAME',
    'source': 'pre-wrapper-scan',
    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'description': 'Found $d outside WAI-Spoke/sessions/. Likely misplaced. Verify and move or delete.'
}
import os; os.makedirs('$PROJECT_DIR/WAI-Spoke/lugs/bytype/signal/undelivered', exist_ok=True)
with open('$PROJECT_DIR/WAI-Spoke/lugs/bytype/signal/undelivered/signal-pre-wrapper-anomaly-${TS}-v1.json', 'w') as f:
    json.dump(lug, f, indent=2)
" 2>/dev/null && ANOMALIES=$((ANOMALIES + 1))
    done

    if [[ -f "$PROJECT_DIR/track.jsonl" ]]; then
        TS=$(date +%s)
        python3 -c "
import json, datetime
lug = {
    'id': 'signal-pre-wrapper-anomaly-${TS}-v1',
    'type': 'signal',
    'status': 'undelivered',
    'title': 'Anomaly: track.jsonl found at project root',
    'source': 'pre-wrapper-scan',
    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'description': 'Found track.jsonl at $PROJECT_DIR root — should be under WAI-Spoke/sessions/.'
}
import os; os.makedirs('$PROJECT_DIR/WAI-Spoke/lugs/bytype/signal/undelivered', exist_ok=True)
with open('$PROJECT_DIR/WAI-Spoke/lugs/bytype/signal/undelivered/signal-pre-wrapper-anomaly-${TS}-v1.json', 'w') as f:
    json.dump(lug, f, indent=2)
" 2>/dev/null && ANOMALIES=$((ANOMALIES + 1))
    fi

    [[ $ANOMALIES -gt 0 ]] && echo "[wai-enter] Anomalies: $ANOMALIES signal lug(s) created — handle at wakeup"
fi

# ── 5. Auto-fix inside WAI-Spoke/ only ──────────────────────────────────────
mkdir -p "$PROJECT_DIR/WAI-Spoke/runtime"

for d in "$PROJECT_DIR/WAI-Spoke/session-"*/; do
    [[ -d "$d" ]] || continue
    NAME=$(basename "$d")
    mkdir -p "$PROJECT_DIR/WAI-Spoke/sessions"
    mv "$d" "$PROJECT_DIR/WAI-Spoke/sessions/$NAME" 2>/dev/null \
        && echo "[wai-enter] Fixed: moved $NAME → WAI-Spoke/sessions/"
done

if [[ -d "$PROJECT_DIR/.claude/hooks" ]]; then
    chmod +x "$PROJECT_DIR/.claude/hooks/"*.sh 2>/dev/null || true
fi

# ── 6. Launch tool ──────────────────────────────────────────────────────────
TOOL="${1:-}"
if [[ -z "$TOOL" ]]; then
    read -r -p "[wai-enter] Tool to launch (claude/gemini/codex/uvx): " TOOL
fi

if ! command -v "$TOOL" >/dev/null 2>&1; then
    echo "[wai-enter] ERROR: tool '$TOOL' not found in PATH"
    exit 1
fi

echo "[wai-enter] Launching $TOOL..."
"$TOOL" "${@:2}"

# ── 7. Post-exit: regenerate brief for next session ─────────────────────────
if [[ -f "$PROJECT_DIR/wai-exit.sh" ]]; then
    "$PROJECT_DIR/wai-exit.sh"
fi
