#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# WAI CANONICAL — wai-enter.sh
# Source:   /home/mario/projects/basher/wai-enter.sh
# Version:  basher (single source of truth — update here, all projects follow)
# Aliases:  wcl, wgm, wcx, woc, wpup, wqw → point here via ai-tools.sh
# Spokes:   each project/wai-enter.sh is a thin wrapper that exec's this file
# ─────────────────────────────────────────────────────────────────────────────
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

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
PROJECT_DIR="${PWD}"

# ── Detect project type ──────────────────────────────────────────────────────
IS_HUB=false
IS_SPOKE=false
[[ -d "$PROJECT_DIR/WAI-Hub" ]] && IS_HUB=true
[[ -f "$PROJECT_DIR/WAI-Spoke/WAI-State.json" ]] && IS_SPOKE=true

# Walk up from CWD if not found at the root level
if [[ "$IS_HUB" == "false" && "$IS_SPOKE" == "false" ]]; then
    _wai_walk="$(dirname "$PROJECT_DIR")"
    while [[ "$_wai_walk" != "/" ]]; do
        if [[ -f "$_wai_walk/WAI-Spoke/WAI-State.json" ]]; then
            PROJECT_DIR="$_wai_walk"; IS_SPOKE=true; break
        elif [[ -d "$_wai_walk/WAI-Hub" ]]; then
            PROJECT_DIR="$_wai_walk"; IS_HUB=true; break
        fi
        _wai_walk="$(dirname "$_wai_walk")"
    done
    unset _wai_walk
fi

# Truly not a WAI project — launch tool directly (no SCRIPT_DIR fallback;
# falling back to the canonical's own WAI-State injected basher's state into
# unrelated directories).
if [[ "$IS_HUB" == "false" && "$IS_SPOKE" == "false" ]]; then
    exec "${1:-claude}" "${@:2}"
fi

# Validate: detected project must be registered in hub-registry.json.
# Prevents WAI scaffolding from running in stale clones, abandoned spokes, or
# directories that happen to contain a WAI-Spoke/ but aren't part of the fleet.
if [[ "$IS_SPOKE" == "true" ]]; then
    _wai_hub_path=$(jq -r '.wheel.hub_path // ""' "$PROJECT_DIR/WAI-Spoke/WAI-State.json" 2>/dev/null)
    if [[ -n "$_wai_hub_path" && -f "$_wai_hub_path/hub-registry.json" ]]; then
        _wai_registered=$(PROJECT_DIR="$PROJECT_DIR" REG="$_wai_hub_path/hub-registry.json" python3 -c "
import json, os
try:
    target = os.path.realpath(os.environ['PROJECT_DIR'])
    reg = json.load(open(os.environ['REG']))
    for w in reg.get('wheels', []):
        p = w.get('path', '')
        if p and os.path.realpath(p) == target:
            print('yes'); break
    else:
        print('no')
except Exception:
    print('unknown')
" 2>/dev/null)
        if [[ "$_wai_registered" == "no" ]]; then
            printf "  \e[33m◇\e[0m  WAI: %s not in hub-registry — launching %s without WAI wrapper\n" \
                "$PROJECT_DIR" "${1:-claude}" >&2
            unset _wai_hub_path _wai_registered
            exec "${1:-claude}" "${@:2}"
        fi
    fi
    unset _wai_hub_path _wai_registered
fi

# ── Style helpers ────────────────────────────────────────────────────────────
_W_BOLD='\e[1m'; _W_DIM='\e[2m'; _W_RST='\e[0m'
_W_GRN='\e[32m'; _W_YLW='\e[33m'; _W_CYN='\e[36m'
_wai_ok()   { printf "  ${_W_GRN}●${_W_RST}  %-12s %s\n" "$1" "$2"; }
_wai_warn() { printf "  ${_W_YLW}◇${_W_RST}  %-12s %s\n" "$1" "$2"; }
_wai_info() { printf "  ${_W_DIM}·${_W_RST}  %-12s %s\n" "$1" "$2"; }
_WAI_BRIEF_STATUS="scanning"

# ── 1. Generate fresh wakeup brief ──────────────────────────────────────────
if [[ "$IS_HUB" == "true" && -f "$PROJECT_DIR/tools/octo_brief.py" ]]; then
    if python3 "$PROJECT_DIR/tools/octo_brief.py" 2>/dev/null; then
        _WAI_BRIEF_STATUS="ready"
    else
        _WAI_BRIEF_STATUS="failed (live scan)"
    fi
elif [[ -f "$PROJECT_DIR/tools/generate_wakeup_brief.py" ]]; then
    if python3 "$PROJECT_DIR/tools/generate_wakeup_brief.py" 2>/dev/null; then
        _WAI_BRIEF_STATUS="ready"
    else
        _WAI_BRIEF_STATUS="failed (live scan)"
    fi
else
    _WAI_BRIEF_STATUS="generator missing (live scan)"
fi

# ── 1b. Intent probe (spoke sessions only) ──────────────────────────────────
# Detect continue mode: -c in tool args skips menu and opening prompt
_CONTINUE_MODE=false
for _arg in "${@:2}"; do [[ "$_arg" == "-c" ]] && _CONTINUE_MODE=true && break; done

if [[ "$IS_SPOKE" == "true" ]]; then
    _INTENT_FILE="$PROJECT_DIR/WAI-Spoke/runtime/session-intent.json"
    _BRIEF_FILE="$PROJECT_DIR/WAI-Spoke/wakeup-brief.json"
    _STATE_FILE="$PROJECT_DIR/WAI-Spoke/WAI-State.json"
    _IS_FRAMEWORK=$(jq -r '(.wheel.qualifiers.project_types // []) | contains(["framework"])' "$_STATE_FILE" 2>/dev/null || echo "false")

    _SPOKES_FILE="/tmp/wai-enter-spokes-$$.json"
    _HAS_METRICS=false
    if [[ -f "$PROJECT_DIR/tools/wai_enter_metrics.py" ]]; then
        _METRICS=$(python3 "$PROJECT_DIR/tools/wai_enter_metrics.py" \
            --spoke-path "$PROJECT_DIR" --spokes-out "$_SPOKES_FILE" 2>/dev/null)
        _HAS_METRICS=true
    else
        _METRICS=""
    fi
    _TEACH=$(echo "$_METRICS" | grep '^teach=' | cut -d= -f2)
    _SESSION_HINT=$(echo "$_METRICS" | grep '^session=' | cut -d= -f2)
    _SP_STATUS=$(echo "$_METRICS" | grep '^sp_status=' | cut -d= -f2)
    _SP_LUG=$(echo "$_METRICS" | grep '^sp_lug=' | cut -d= -f2)
    _SP_NOTE=$(echo "$_METRICS" | grep '^sp_note=' | cut -d= -f2)
    _BLOCKED=$(echo "$_METRICS" | grep '^blocked=' | cut -d= -f2)
    _TEACH_MANUAL=$(echo "$_METRICS" | grep '^manual_teach=' | cut -d= -f2)
    _SPOKES=$(echo "$_METRICS" | grep '^spokes_count=' | cut -d= -f2)
    _INC_UNGROOMED=$(echo "$_METRICS" | grep '^incoming_ungroomed=' | cut -d= -f2)
    _INC_HAIKU=$(echo "$_METRICS" | grep '^incoming_haiku_groomed=' | cut -d= -f2)
    _INC_SONNET=$(echo "$_METRICS" | grep '^incoming_sonnet_groomed=' | cut -d= -f2)
    _ATTN_OZI=$(echo "$_METRICS" | grep '^attn_from_ozi=' | cut -d= -f2)
    _STALLED=$(echo "$_METRICS" | grep '^stalled_in_progress=' | cut -d= -f2)
    _INTERRUPTED=$(echo "$_METRICS" | grep '^interrupted_count=' | cut -d= -f2)
    : "${_TEACH:=0}" "${_SESSION_HINT:=unknown}" "${_SP_STATUS:=}" "${_SP_LUG:=}" \
      "${_SP_NOTE:=}" "${_BLOCKED:=0}" "${_TEACH_MANUAL:=0}" "${_SPOKES:=0}" \
      "${_INC_UNGROOMED:=0}" "${_INC_HAIKU:=0}" "${_INC_SONNET:=0}" \
      "${_ATTN_OZI:=0}" "${_STALLED:=0}" "${_INTERRUPTED:=0}"

    # ── Brief fallback: fill counts when metrics script absent ────────────────
    # Runs AFTER defaults so it overwrites zeros with real values.
    # Savepoint and lug counts are read separately to avoid read splitting on
    # spaces inside the savepoint note.
    if [[ "$_HAS_METRICS" == "false" ]]; then
        # Savepoint: brief first, WAI-State fallback if brief has none.
        # IFS=$'\x1f' on the read so spaces in the note don't split fields.
        IFS=$'\x1f' read -r _SP_STATUS _SP_LUG _SP_NOTE < <(python3 -c "
import json
def _sp_from(sp):
    if not sp: return '', '', ''
    return (sp.get('status', ''),
            sp.get('lug_id', '') or sp.get('session_id', ''),
            (sp.get('resume_note', '') or '').replace('\n',' '))
status = lug_id = note = ''
try:
    b = json.load(open('$PROJECT_DIR/WAI-Spoke/wakeup-brief.json'))
    status, lug_id, note = _sp_from(b.get('savepoint'))
except Exception:
    pass
if not status:
    try:
        s = json.load(open('$PROJECT_DIR/WAI-Spoke/WAI-State.json'))
        status, lug_id, note = _sp_from(s.get('_savepoint'))
    except Exception:
        pass
print('\x1f'.join([status, lug_id, note]))
" 2>/dev/null)

        # Lug counts: scan bytype/*/open/, skip signals/epics/specs (non-executable)
        read -r _INC_HAIKU _INC_SONNET _INC_UNGROOMED _BLOCKED < <(python3 -c "
import json, glob
_SKIP_TYPES = {'signal', 'epic', 'spec', 'phone-home'}
haiku = sonnet = ungroomed = blocked_ct = 0
try:
    for f in glob.glob('$PROJECT_DIR/WAI-Spoke/lugs/bytype/*/open/*.json'):
        try:
            d = json.load(open(f))
            ltype = (d.get('type') or d.get('ty') or '').lower()
            if ltype in _SKIP_TYPES:
                continue
            model = (d.get('model_fit') or d.get('model', '')).lower()
            if 'haiku' in model:
                haiku += 1
            elif model:
                sonnet += 1
            else:
                ungroomed += 1
        except Exception:
            pass
    for _ in glob.glob('$PROJECT_DIR/WAI-Spoke/lugs/bytype/*/blocked/*.json'):
        blocked_ct += 1
except Exception:
    pass
print(haiku, sonnet, ungroomed, blocked_ct)
" 2>/dev/null)
        : "${_INC_HAIKU:=0}" "${_INC_SONNET:=0}" "${_INC_UNGROOMED:=0}" "${_BLOCKED:=0}"
    fi

    # ── Dedup guard: repair manual/ teachings missing from processed/ ─────────
    # If a teaching lands in manual/ without a matching processed/ entry it gets
    # double-counted. Silently self-heal then recount.
    _MANUAL_DIR="$PROJECT_DIR/WAI-Spoke/seed/ingest/manual"
    _PROCESSED_DIR="$PROJECT_DIR/WAI-Spoke/seed/ingest/processed"
    if [[ -d "$_MANUAL_DIR" ]]; then
        for _f in "$_MANUAL_DIR"/*.teaching; do
            [[ -e "$_f" ]] || continue
            _fname="$(basename "$_f")"
            if [[ ! -f "$_PROCESSED_DIR/$_fname" ]]; then
                cp "$_f" "$_PROCESSED_DIR/$_fname" 2>/dev/null
            fi
        done
        _TEACH_MANUAL=$(python3 -c "
import glob, os
manual = {os.path.basename(f) for f in glob.glob('$_MANUAL_DIR/*.teaching')}
processed = {os.path.basename(f) for f in glob.glob('$_PROCESSED_DIR/*.teaching')}
print(len(manual - processed))
" 2>/dev/null || echo "0")
    fi

    # ── Aggregates ───────────────────────────────────────────────────────────
    _ATTN=$(( _ATTN_OZI + _TEACH_MANUAL + _STALLED + _INTERRUPTED + _BLOCKED ))
    _WORK=$(( _INC_UNGROOMED + _INC_HAIKU + _INC_SONNET ))

    if [[ "$_CONTINUE_MODE" == "true" ]]; then
        # -c flag: auto-select highest-priority intent
        if [[ "$_SP_STATUS" == "pending" ]]; then
            _INTENT="savepoint"   ; _INTENT_LABEL="Resume — $_SP_LUG"
        elif (( _SPOKES > 0 )); then
            _INTENT="spokes"      ; _INTENT_LABEL="Open Messages to You (${_SPOKES})"
        elif (( _ATTN > 0 )); then
            _INTENT="attention"   ; _INTENT_LABEL="Needs Your Action (${_ATTN})"
        elif (( _WORK > 0 )); then
            _INTENT="ready_work"  ; _INTENT_LABEL="Ready to Process (${_WORK})"
        else
            _INTENT="raw"         ; _INTENT_LABEL="Raw — no opening prompt"
        fi
        _INTENT_CHOICE=""
        printf "  ${_W_DIM}→ auto-selected: %s${_W_RST}\n" "$_INTENT_LABEL"
    else
        # Drain typeahead buffered during brief gen / basher audit / other pre-launch steps.
        # Keystrokes pressed while waiting get consumed by read -rsn1 and select unintended options.
        [[ -t 0 ]] && read -r -t 0.15 -n 512 _ 2>/dev/null || true

        _READY_ACTION=""

        # ── Header ───────────────────────────────────────────────────────────
        printf "\n"
        printf "  ${_W_BOLD}WAI · Session Start${_W_RST}\n"
        printf "  ${_W_DIM}────────────────────────────────────────────${_W_RST}\n"
        if [[ "$_WAI_BRIEF_STATUS" == "ready" ]]; then
            _wai_ok  "Brief" "ready"
        else
            _wai_warn "Brief" "$_WAI_BRIEF_STATUS"
        fi
        printf "\n"

        # ── Menu ─────────────────────────────────────────────────────────────
        # Enter (↵) — resume savepoint when pending; else highest-priority default
        # Space / [r] — Raw (new session, no opening prompt)
        printf "  ${_W_DIM}How do you want to start?${_W_RST}\n\n"

        # Savepoint (show when pending)
        # Format: "  [x]  %-20s  description"  — descriptions align at col 29
        if [[ "$_SP_STATUS" == "pending" ]]; then
            printf "  ${_W_BOLD}[↵]${_W_RST}  %-20s  ${_W_DIM}%s%s${_W_RST}\n" \
                "Resume" "$_SP_LUG" "${_SP_NOTE:+  — \"$_SP_NOTE\"}"
        fi

        # Open Messages to You — cross-spoke items (hide when zero)
        if (( _SPOKES > 0 )); then
            printf "  ${_W_BOLD}[a]${_W_RST}  %-20s  ${_W_DIM}(%d)${_W_RST}\n" "Open Messages to You" "$_SPOKES"
            if [[ -f "$_SPOKES_FILE" ]]; then
                python3 -c "
import json
try:
    items = json.load(open('$_SPOKES_FILE'))
    for item in items:
        label  = item.get('urgency_label', 'Normal')[:8]
        sender = item.get('sender_name', '?')[:18]
        title  = item.get('title', '')[:36]
        print('       \033[2m{:>8}  {:18}  {}\033[0m'.format(label, sender, title))
except: pass
" 2>/dev/null
            fi
        fi

        # Needs Your Action — lugs requiring human review (hide when zero)
        if (( _ATTN > 0 )); then
            printf "  ${_W_BOLD}[b]${_W_RST}  %-20s  ${_W_DIM}(%d)${_W_RST}\n" "Needs Your Action" "$_ATTN"
            (( _ATTN_OZI > 0 ))     && printf "       ${_W_DIM}%3d  Ozi decision needed${_W_RST}\n" "$_ATTN_OZI"
            (( _TEACH_MANUAL > 0 )) && printf "       ${_W_DIM}%3d  manual teachings${_W_RST}\n" "$_TEACH_MANUAL"
            (( _STALLED > 0 ))      && printf "       ${_W_DIM}%3d  stalled in-progress${_W_RST}\n" "$_STALLED"
            (( _INTERRUPTED > 0 ))  && printf "       ${_W_DIM}%3d  interrupted sessions${_W_RST}\n" "$_INTERRUPTED"
            (( _BLOCKED > 0 ))      && printf "       ${_W_DIM}%3d  blocked lugs${_W_RST}\n" "$_BLOCKED"
        fi

        # Ready to Process — autopilot-servable queue (hide when zero)
        if (( _WORK > 0 )); then
            printf "  ${_W_BOLD}[c]${_W_RST}  %-20s  ${_W_DIM}(%d)${_W_RST}\n" "Ready to Process" "$_WORK"
            (( _INC_UNGROOMED > 0 )) && printf "       ${_W_DIM}%3d  needs Ozi grooming${_W_RST}\n" "$_INC_UNGROOMED"
            (( _INC_HAIKU > 0 ))     && printf "       ${_W_DIM}%3d  haiku / autonomous${_W_RST}\n" "$_INC_HAIKU"
            (( _INC_SONNET > 0 ))    && printf "       ${_W_DIM}%3d  sonnet builds${_W_RST}\n" "$_INC_SONNET"
        fi

        printf "  ${_W_BOLD}[r]${_W_RST}  %-20s  ${_W_DIM}no opening prompt${_W_RST}\n" "Raw"
        printf "  ${_W_BOLD}[q]${_W_RST}  Quit\n"
        printf "\n  ${_W_DIM}────────────────────────────────────────────${_W_RST}\n"
        printf "  > "

        while true; do
            read -rsn1 _INTENT_CHOICE
            case "${_INTENT_CHOICE}" in
                a|A)
                    if (( _SPOKES > 0 )); then
                        printf "a\n"; _INTENT="spokes"; _INTENT_LABEL="Open Messages to You"; break
                    fi ;;
                b|B)
                    if (( _ATTN > 0 )); then
                        printf "b\n"; _INTENT="attention"; _INTENT_LABEL="Needs Your Action"; break
                    fi ;;
                c|C)
                    if (( _WORK > 0 )); then
                        printf "c\n"; _INTENT="ready_work"; _INTENT_LABEL="Ready to Process"; break
                    fi ;;
                " "|r|R)
                    # Space or [r] — Raw (new session, no opening prompt)
                    printf "r\n"; _INTENT="raw"; _INTENT_LABEL="Raw — no opening prompt"; break ;;
                q|Q)
                    printf "quit\n"; echo; rm -f "$_SPOKES_FILE"; return 0 2>/dev/null || exit 0 ;;
                "")
                    # Enter — resume savepoint if pending, else highest-priority default
                    printf "\n"
                    if [[ "$_SP_STATUS" == "pending" ]]; then
                        _INTENT="savepoint"  ; _INTENT_LABEL="Resume — $_SP_LUG"
                    elif (( _SPOKES > 0 )); then
                        _INTENT="spokes"     ; _INTENT_LABEL="Open Messages to You"
                    elif (( _ATTN > 0 )); then
                        _INTENT="attention"  ; _INTENT_LABEL="Needs Your Action"
                    elif (( _WORK > 0 )); then
                        _INTENT="ready_work" ; _INTENT_LABEL="Ready to Process"
                    else
                        _INTENT="raw"        ; _INTENT_LABEL="Raw — no opening prompt"
                    fi
                    break ;;
                *) ;; # invalid key — re-prompt silently
            esac
        done

        # ── Sub-menu: Ready to Process ────────────────────────────────────────
        # Shown when [c] or Enter-default selects ready_work.
        # Enter / [r] — Review items (opens claude with ready_work prompt)
        # [a]         — Send to Autopilot (basher autopilot run --budget N, then exit)
        if [[ "$_INTENT" == "ready_work" ]]; then
            printf "\n"
            printf "  ${_W_DIM}Ready to Process — what next?${_W_RST}\n\n"
            printf "  ${_W_BOLD}[r]${_W_RST}  %-22s  ${_W_DIM}Enter${_W_RST}\n" "Review items"
            printf "  ${_W_BOLD}[a]${_W_RST}  %-22s  ${_W_DIM}runs: basher autopilot --budget %d${_W_RST}\n" \
                "Send to Autopilot" "$_WORK"
            printf "  ${_W_BOLD}[q]${_W_RST}  Quit\n"
            printf "\n  > "

            while true; do
                read -rsn1 _SUB_CHOICE
                case "$_SUB_CHOICE" in
                    r|R|"")
                        printf "r\n"; _READY_ACTION="review"; break ;;
                    a|A)
                        printf "a\n"; _READY_ACTION="autopilot"; break ;;
                    q|Q)
                        printf "quit\n"; echo; rm -f "$_SPOKES_FILE"
                        return 0 2>/dev/null || exit 0 ;;
                    *) ;; # invalid key — re-prompt silently
                esac
            done

            if [[ "$_READY_ACTION" == "autopilot" ]]; then
                rm -f "$_SPOKES_FILE"
                _AUTOPILOT_SCRIPT="$SCRIPT_DIR/scripts/autopilot.sh"
                if [[ -f "$_AUTOPILOT_SCRIPT" ]]; then
                    printf "\n  ${_W_DIM}Sending %d item(s) to autopilot...${_W_RST}\n\n" "$_WORK"
                    bash "$_AUTOPILOT_SCRIPT" run --budget "$_WORK"
                else
                    printf "  ${_W_YLW}ERROR:${_W_RST} autopilot.sh not found at %s\n" "$_AUTOPILOT_SCRIPT"
                fi
                return 0 2>/dev/null || exit 0
            fi
            # _READY_ACTION == "review" — fall through to normal launch with ready_work prompt
        fi
    fi

    _SP_RESUMED="false"
    [[ "$_INTENT" == "savepoint" ]] && _SP_RESUMED="true"

    mkdir -p "$PROJECT_DIR/WAI-Spoke/runtime"
    _INTENT="$_INTENT" _INTENT_LABEL="$_INTENT_LABEL" _SESSION_HINT="$_SESSION_HINT" \
    _SP_RESUMED="$_SP_RESUMED" _INTENT_CHOICE="$_INTENT_CHOICE" _INTENT_FILE="$_INTENT_FILE" \
    python3 -c "
import json, datetime, os
data = {
    'intent': os.environ['_INTENT'],
    'intent_label': os.environ['_INTENT_LABEL'],
    'selected_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'session_id_hint': os.environ['_SESSION_HINT'],
    'savepoint_resumed': os.environ['_SP_RESUMED'] == 'true',
    'raw_choice': os.environ['_INTENT_CHOICE']
}
with open(os.environ['_INTENT_FILE'], 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null

    if [[ "$_CONTINUE_MODE" == "false" ]]; then
        case "$_INTENT" in
            savepoint)
                _OPEN_PROMPT="Resume savepoint ${_SP_LUG}. Read WAI-Spoke/WAI-State.json (._savepoint) for the recorded next-action and continue from there.${_SP_NOTE:+ Prior-session note: ${_SP_NOTE}}" ;;
            spokes)
                _OPEN_PROMPT=$(python3 -c "
import json
try:
    items = json.load(open('$_SPOKES_FILE'))
    out = ['Triage {} open lug(s) delivered from other spokes (WAI-Spoke/lugs/incoming/).'.format(len(items)), '', 'Items:']
    for i, item in enumerate(items, 1):
        out.append('  {}. [{}] from {}: {}'.format(
            i, item.get('urgency_label','Normal'), item.get('sender_name','?'), item.get('title','')))
    out += ['', 'For each lug:',
            '  1. Read the file in WAI-Spoke/lugs/incoming/.',
            '  2. Evaluate fit against this spoke mission and current priorities.',
            '  3. Decide: accept (move to WAI-Spoke/lugs/bytype/{type}/open/), defer (add deferred_until note), or reject (write a rejection lug back to source_spoke with the reason).',
            '',
            'Walk through them in order. State the intended decision for each before acting so I can interject.']
    print('\n'.join(out))
except Exception:
    print('Triage the lugs in WAI-Spoke/lugs/incoming/: read each, decide accept/defer/reject, and route accordingly. Summarize each decision before acting.')
" 2>/dev/null) ;;
            attention)
                _OPEN_PROMPT=$(
                    printf "Resolve %d item(s) needing decision in this spoke. For each category, take the action below:\n\n" "$_ATTN"
                    (( _ATTN_OZI > 0 ))     && printf "Ozi-flagged (%d): read each lug under WAI-Spoke/lugs/bytype/*/ozi_review/. Decide accept / decompose / reject and record the reason on the lug.\n\n" "$_ATTN_OZI"
                    (( _TEACH_MANUAL > 0 )) && printf "Manual teachings (%d): read each .teaching file in WAI-Spoke/seed/ingest/manual/. Recommend adopt or reject with reasoning, then move decided files into seed/ingest/processed/.\n\n" "$_TEACH_MANUAL"
                    (( _STALLED > 0 ))      && printf "Stalled in-progress (%d): for each lug in_progress >24h, choose unstick / retry / defer / close and update its status with a note.\n\n" "$_STALLED"
                    (( _INTERRUPTED > 0 ))  && printf "Interrupted sessions (%d): for each session under WAI-Spoke/sessions/ marked INTERRUPTED, read its track.jsonl and recommend resume / complete-and-close / abandon-and-close with a one-line rationale.\n\n" "$_INTERRUPTED"
                    (( _BLOCKED > 0 ))      && printf "Blocked lugs (%d): for each lug in WAI-Spoke/lugs/bytype/*/blocked/, verify the blocking lug still exists and is unresolved. If clear, move the lug back to open/. If still real, document why on the lug.\n\n" "$_BLOCKED"
                    printf "Walk the categories in order. Before acting on individual items, state the intended decision so I can interject."
                ) ;;
            ready_work)
                _OPEN_PROMPT=$(
                    printf "Process %d item(s) in the work queue.\n\n" "$_WORK"
                    (( _INC_UNGROOMED > 0 )) && printf "Ungroomed (%d): in WAI-Spoke/lugs/incoming/. Read each, score effort (1-10), assign model_fit (haiku/sonnet/opus), and route to WAI-Spoke/lugs/bytype/{type}/open/. Report each scoring decision before routing.\n\n" "$_INC_UNGROOMED"
                    (( _INC_HAIKU > 0 ))     && printf "Haiku-ready (%d): autonomous builds in WAI-Spoke/lugs/bytype/*/open/ with model_fit=haiku.\n\n" "$_INC_HAIKU"
                    (( _INC_SONNET > 0 ))    && printf "Sonnet-ready (%d): builds in WAI-Spoke/lugs/bytype/*/open/ with model_fit=sonnet.\n\n" "$_INC_SONNET"
                    printf "Steps:\n"
                    printf "  1. Groom all ungroomed items first.\n"
                    printf "  2. Then propose: launch \`basher autopilot run --budget %d\` for the haiku/sonnet queue, or hand specific items back for review.\n" "$_WORK"
                ) ;;
            raw|*)
                _OPEN_PROMPT="" ;;
        esac
        if [[ -n "$_OPEN_PROMPT" ]]; then
            printf "\n  ${_W_DIM}Opening prompt:${_W_RST}\n"
            printf "  ${_W_DIM}──────────────────────────────────────────${_W_RST}\n"
            printf '%s\n' "$_OPEN_PROMPT" | while IFS= read -r _wai_line; do
                printf "  ${_W_DIM}%s${_W_RST}\n" "$_wai_line"
            done
            printf "  ${_W_DIM}──────────────────────────────────────────${_W_RST}\n\n"
        fi
    fi

    rm -f "$_SPOKES_FILE"
fi

# ── 2. Refresh stale context feeds in background ────────────────────────────
if [[ "$IS_HUB" == "true" && -f "$PROJECT_DIR/tools/hub_context_refresh.py" ]]; then
    mkdir -p "$HOME/.claude/logs"
    python3 "$PROJECT_DIR/tools/hub_context_refresh.py" \
        --quiet \
        >> "$HOME/.claude/logs/hub-context-refresh-$(date +%Y%m%d).log" 2>&1 &
    _wai_info "Feeds" "hub refresh running in background"
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
            _wai_info "Feeds" "refreshing (last: $LAST_RUN)"
        fi
    fi
fi

# ── 3. Hub: check outbox for pending deliveries ──────────────────────────────
if [[ "$IS_HUB" == "true" ]]; then
    OUTBOX="$PROJECT_DIR/WAI-Hub/outbox"
    if [[ -d "$OUTBOX" ]]; then
        PENDING=$(find "$OUTBOX" -mindepth 2 -maxdepth 2 -name "*.json" 2>/dev/null | wc -l)
        [[ "$PENDING" -gt 0 ]] && _wai_warn "Outbox" "$PENDING pending deliveries"
    fi
fi

# ── 3. Spoke: hook completeness check ───────────────────────────────────────
if [[ "$IS_SPOKE" == "true" && -f "$PROJECT_DIR/.claude/settings.json" ]]; then
    _CONFIG_GAPS=$(python3 -c "
import json, sys
try:
    d = json.load(open('$PROJECT_DIR/.claude/settings.json'))
    required = {'SessionStart','PreToolUse','Stop','PreCompact','UserPromptSubmit'}
    missing = required - set(d.get('hooks',{}).keys())
    deny = d.get('permissions',{}).get('deny',[])
    if missing:
        print('hooks: ' + ', '.join(sorted(missing)))
    if not deny:
        print('deny-rules: none configured')
except: pass
" 2>/dev/null)
    if [[ -n "$_CONFIG_GAPS" ]]; then
        _wai_warn "Config" "gaps detected — run: basher tools update current"
        echo "$_CONFIG_GAPS" | while IFS= read -r line; do
            printf "         ${_W_DIM}%s${_W_RST}\n" "$line"
        done
        echo ""
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
        _wai_warn "Basher" "config changes detected — see wakeup blurb"
    else
        _wai_ok "Basher" "OK"
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

    [[ $ANOMALIES -gt 0 ]] && _wai_warn "Anomalies" "$ANOMALIES signal lug(s) created — handle at wakeup"
fi

# ── 5. Auto-fix inside WAI-Spoke/ only ──────────────────────────────────────
mkdir -p "$PROJECT_DIR/WAI-Spoke/runtime"

for d in "$PROJECT_DIR/WAI-Spoke/session-"*/; do
    [[ -d "$d" ]] || continue
    NAME=$(basename "$d")
    mkdir -p "$PROJECT_DIR/WAI-Spoke/sessions"
    mv "$d" "$PROJECT_DIR/WAI-Spoke/sessions/$NAME" 2>/dev/null \
        && _wai_info "Fixed" "moved $NAME → WAI-Spoke/sessions/"
done

if [[ -d "$PROJECT_DIR/.claude/hooks" ]]; then
    chmod +x "$PROJECT_DIR/.claude/hooks/"*.sh 2>/dev/null || true
fi

# ── 6. Launch tool ──────────────────────────────────────────────────────────
TOOL="${1:-}"
if [[ -z "$TOOL" ]]; then
    read -r -p "  Tool to launch (claude/gemini/codex/uvx): " TOOL
fi

if ! command -v "$TOOL" >/dev/null 2>&1; then
    printf "  ${_W_YLW}ERROR:${_W_RST} tool '%s' not found in PATH\n" "$TOOL"
    exit 1
fi

# Default claude to sonnet unless --model already supplied.
# ~/.claude.json pins opus globally; wcl-launched sessions should default to sonnet.
_TOOL_ARGS=("${@:2}")
if [[ "$TOOL" == "claude" ]]; then
    _wai_has_model=false
    for _a in "${_TOOL_ARGS[@]}"; do
        if [[ "$_a" == "--model" || "$_a" == --model=* ]]; then
            _wai_has_model=true; break
        fi
    done
    if [[ "$_wai_has_model" == "false" ]]; then
        _TOOL_ARGS=(--model sonnet "${_TOOL_ARGS[@]}")
    fi
    unset _wai_has_model _a
fi

printf "\n  ${_W_DIM}Launching %s...${_W_RST}\n\n" "$TOOL"
if [[ -n "${_OPEN_PROMPT:-}" ]]; then
    "$TOOL" "$_OPEN_PROMPT" "${_TOOL_ARGS[@]}"
else
    "$TOOL" "${_TOOL_ARGS[@]}"
fi

# ── 7. Post-exit: regenerate brief for next session ─────────────────────────
if [[ -f "$PROJECT_DIR/wai-exit.sh" ]]; then
    "$PROJECT_DIR/wai-exit.sh"
fi
