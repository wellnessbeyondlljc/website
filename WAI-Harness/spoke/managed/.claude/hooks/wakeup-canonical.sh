#!/bin/bash
#
# WAI Session Start Hook
# Runs at Claude Code session start — before first user message.
# Pre-computes wakeup data so Claude doesn't need tool calls for init work.
#
# Outputs: <wai-session-init> block injected into session context
#

PROJECT_DIR="${WAI_PROJECT_DIR:-${CODEX_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$(pwd)}}}"
# Mode-aware data-plane base (canon v4): v4-only -> WAI-Harness/spoke/local ; else v3 WAI-Spoke.
if [[ -d "$PROJECT_DIR/WAI-Harness/spoke/local" && ! -d "$BASE" ]]; then
  BASE="$PROJECT_DIR/WAI-Harness/spoke/local"
elif [[ "${WAI_HARNESS_MODE:-}" == v4* && -d "$PROJECT_DIR/WAI-Harness/spoke/local" ]]; then
  BASE="$PROJECT_DIR/WAI-Harness/spoke/local"
else
  BASE="$BASE"
fi
STATE_FILE="$BASE/WAI-State.json"
BASE_REL="${BASE#$PROJECT_DIR/}"   # data-plane path relative to project (for display)

# Auto-init: if no WAI-State.json but template exists, bootstrap WAI-Spoke/
TEMPLATE_FILE="$PROJECT_DIR/templates/spoke/WAI-State.json.template"
if [[ ! -f "$STATE_FILE" && -f "$TEMPLATE_FILE" ]]; then
  mkdir -p "$BASE"
  cp "$TEMPLATE_FILE" "$STATE_FILE"
  # Create essential directories
  mkdir -p "$BASE/sessions"
  mkdir -p "$BASE/lugs/bytype/epic/open"
  mkdir -p "$BASE/lugs/bytype/task/open"
  mkdir -p "$BASE/lugs/bytype/bug/open"
  mkdir -p "$BASE/lugs/bytype/feature/open"
  mkdir -p "$BASE/lugs/bytype/signal/undelivered"
  mkdir -p "$BASE/lugs/bytype/other/open"
  mkdir -p "$BASE/seed/ingest"
  mkdir -p "$BASE/runtime"
fi

# Exit silently if still no state file (not a WAI project)
[[ ! -f "$STATE_FILE" ]] && exit 0

# ── 0.5. Apply pending signals v2 (before wai-session-init) ─────────────────
# Behavioral patches in WAI-Spoke/signals/inbound/ are applied at session start.
# They are plain-language directives included in the CONTEXT HEALTH block.
SIGNALS_APPLIED_COUNT=0
SIGNALS_APPLIED_PATCHES=""
_SIG_REG="$BASE/signals/registry.json"
if [[ -f "$_SIG_REG" && -d "$BASE/signals/inbound" ]]; then
  for _sigfile in "$BASE/signals/inbound/"*.json; do
    [[ -f "$_sigfile" ]] || continue
    _SIG_ID=$(jq -r '.id // ""' "$_sigfile" 2>/dev/null)
    [[ -z "$_SIG_ID" ]] && continue
    _ALREADY=$(jq -r --arg id "$_SIG_ID" '.applied | index($id) // empty' "$_SIG_REG" 2>/dev/null)
    [[ -n "$_ALREADY" ]] && continue
    _SIG_FLAVOR=$(jq -r '.flavor // "delivery"' "$_sigfile" 2>/dev/null)
    _SIG_RISK=$(jq -r '.risk_score // 5' "$_sigfile" 2>/dev/null)
    _SIG_TITLE=$(jq -r '.title // ""' "$_sigfile" 2>/dev/null)
    if [[ "$_SIG_FLAVOR" == "patch" ]]; then
      _SIG_PATCH=$(jq -r '.patch // .description // ""' "$_sigfile" 2>/dev/null | head -c 200)
      SIGNALS_APPLIED_PATCHES="${SIGNALS_APPLIED_PATCHES}\n  [PATCH risk=${_SIG_RISK}] ${_SIG_TITLE}: ${_SIG_PATCH}"
      SIGNALS_APPLIED_COUNT=$((SIGNALS_APPLIED_COUNT + 1))
      _SIG_TMP=$(mktemp)
      _SIG_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
      jq --arg id "$_SIG_ID" --arg ts "$_SIG_TS" \
         '.applied += [$id] | .applied_at[$id] = $ts' \
         "$_SIG_REG" > "$_SIG_TMP" 2>/dev/null && mv "$_SIG_TMP" "$_SIG_REG" || rm -f "$_SIG_TMP"
    fi
  done
fi

# ── 0.6. Signal loop-close: teaching arrived → remove registry entry ─────────
# When a teaching that closes a signal is adopted (appears in processed/), archive
# the signal from inbound/ and remove its registry entry. This closes the loop
# started by impl-signal-hub-trigger-v1 / impl-signal-teaching-autogen-v1.
if [[ -f "$_SIG_REG" ]]; then
  _LC_PROCESSED="$BASE/seed/ingest/processed"
  _LC_ARCHIVE="$BASE/signals/processed"
  _LOOP_CLOSED=""
  for _lcsigfile in "$BASE/signals/inbound/"*.json; do
    [[ -f "$_lcsigfile" ]] || continue
    _LC_ID=$(jq -r '.id // ""' "$_lcsigfile" 2>/dev/null)
    [[ -z "$_LC_ID" ]] && continue
    # A teaching closes this signal if its filename contains the signal id
    _LC_TEACHING=$(ls "$_LC_PROCESSED/"*"${_LC_ID}"*.teaching 2>/dev/null | head -1)
    if [[ -n "$_LC_TEACHING" ]]; then
      _LC_TMP=$(mktemp)
      jq --arg id "$_LC_ID" \
         '.applied = [.applied[] | select(. != $id)] | del(.applied_at[$id])' \
         "$_SIG_REG" > "$_LC_TMP" 2>/dev/null && mv "$_LC_TMP" "$_SIG_REG" || rm -f "$_LC_TMP"
      mkdir -p "$_LC_ARCHIVE"
      mv "$_lcsigfile" "$_LC_ARCHIVE/" 2>/dev/null || true
      _LOOP_CLOSED="$_LOOP_CLOSED $_LC_ID"
    fi
  done
  if [[ -n "$_LOOP_CLOSED" ]]; then
    SIGNALS_APPLIED_PATCHES="${SIGNALS_APPLIED_PATCHES}\n  [LOOP-CLOSED] Teaching matched, signals archived:${_LOOP_CLOSED}"
  fi
fi

# ── Session lane: identify THIS Claude Code session and isolate its tracking ──
# The CC session_id (SessionStart payload on stdin; == transcript basename) is the
# lane key. lane-register is idempotent: a re-fire of the SAME session (IDE reconnect,
# /context) returns the SAME wai_session (SKIP_SESSION_INIT=true), while a genuinely
# concurrent SECOND session gets its OWN wai_session — no date-based identity hijack.
# `timeout` guards the stdin read so a SessionStart with no piped stdin can never hang
# startup; we fall through to the legacy date-based path in that case.
_STDIN=$(timeout 2 cat 2>/dev/null || true)
CC_SID=$(printf '%s' "$_STDIN" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
CC_TRANSCRIPT=$(printf '%s' "$_STDIN" | python3 -c "import json,sys; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
[[ -z "$CC_SID" && -n "$CC_TRANSCRIPT" ]] && CC_SID=$(basename "$CC_TRANSCRIPT" .jsonl)

SESSION_NAME=""
SKIP_SESSION_INIT=false
LANE_OTHERS_COUNT=0
LANE_OTHERS=""
_WG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py"
if [[ -n "$CC_SID" && -f "$_WG" ]]; then
  _LANE=$(python3 "$_WG" lane-register --session "$CC_SID" --base "$BASE" --transcript "$CC_TRANSCRIPT" 2>/dev/null)
  if [[ -n "$_LANE" ]]; then
    SESSION_NAME=$(printf '%s' "$_LANE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('wai_session',''))" 2>/dev/null)
    LANE_OTHERS_COUNT=$(printf '%s' "$_LANE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('others_count',0))" 2>/dev/null)
    LANE_OTHERS=$(printf '%s' "$_LANE" | python3 -c "import json,sys; print(', '.join(json.load(sys.stdin).get('others',[])))" 2>/dev/null)
    _LANE_CREATED=$(printf '%s' "$_LANE" | python3 -c "import json,sys; print(json.load(sys.stdin).get('created',False))" 2>/dev/null)
    [[ "$_LANE_CREATED" == "False" ]] && SKIP_SESSION_INIT=true
  fi
fi

# Legacy fallback: no session id (older CC / direct run). Reuse the same-day completed
# session if present (the old re-entry guard), else mint a date-based name.
if [[ -z "$SESSION_NAME" ]]; then
  _GUARD_FILE="$BASE/runtime/session-guard.json"
  _TODAY_PREFIX="session-$(date +%Y%m%d)"
  if [[ -f "$_GUARD_FILE" ]]; then
    _GC=$(jq -r '.protocol_completed // false' "$_GUARD_FILE" 2>/dev/null || echo "false")
    _GCLOSED=$(jq -r '.session_closed // false' "$_GUARD_FILE" 2>/dev/null || echo "false")
    _GSID=$(jq -r '.session_id // ""' "$_GUARD_FILE" 2>/dev/null || echo "")
    if [[ "$_GC" == "true" && "$_GCLOSED" != "true" && "$_GSID" == "${_TODAY_PREFIX}"* ]]; then
      _GTRACK="$BASE/sessions/$_GSID/track.jsonl"
      if [[ -f "$_GTRACK" && -s "$_GTRACK" ]]; then
        SESSION_NAME="$_GSID"
        SKIP_SESSION_INIT=true
      fi
    fi
  fi
  [[ -z "$SESSION_NAME" ]] && SESSION_NAME="session-$(date +%Y%m%d-%H%M)"
fi

# ── 1. Ensure session directory (lane-register already created it for lanes) ──
SESSION_DIR="$BASE/sessions/$SESSION_NAME"
mkdir -p "$SESSION_DIR"
touch "$SESSION_DIR/track.jsonl"

# ── 1b. Check previous session track integrity ──────────────────────────────
PREV_SESSION_STATUS="FIRST_SESSION"
PREV_SESSION_ID=""
PREV_SESSION=$(ls -1t "$BASE/sessions/" 2>/dev/null | grep -v "^${SESSION_NAME}$" | head -1)
if [[ -n "$PREV_SESSION" ]]; then
  PREV_TRACK="$BASE/sessions/$PREV_SESSION/track.jsonl"
  PREV_SESSION_ID="$PREV_SESSION"
  if [[ -f "$PREV_TRACK" && -s "$PREV_TRACK" ]]; then
    LAST_LINE=$(tail -1 "$PREV_TRACK")
    # CLEAN = completed turn OR explicit closeout event
    if echo "$LAST_LINE" | jq -e '.completed == true or .event == "closeout"' >/dev/null 2>&1; then
      PREV_SESSION_STATUS="CLEAN"
    elif echo "$LAST_LINE" | jq . >/dev/null 2>&1; then
      PREV_SESSION_STATUS="INTERRUPTED"
    else
      PREV_SESSION_STATUS="INTERRUPTED"
    fi
  else
    PREV_SESSION_STATUS="EMPTY"
  fi
fi

# ── 2. Update WAI-State.json with new session ────────────────────────────────
# NOTE: session_count is incremented at closeout only (not here).
# Agent-initiated sessions must not inflate the count.
# Skipped if re-entering an active session (SKIP_SESSION_INIT=true).
# last_session_id/track_path here are a HINT for the fast-path brief only — per-turn
# routing uses the lane registry (concurrency-safe), so a lost update under two
# concurrent sessions is harmless. flock serializes the read-modify-write anyway so
# the file can never interleave into corruption (best-effort: skipped where flock is
# absent, e.g. macOS without util-linux).
if [[ "$SKIP_SESSION_INIT" == "false" ]]; then
_write_state() {
  TMP=$(mktemp)
  jq --arg sid "$SESSION_NAME" --arg base "$BASE_REL" \
     '._session_state.last_session_id = $sid |
      ._session_state.track_path = ($base + "/sessions/" + $sid + "/track.jsonl")' \
     "$STATE_FILE" > "$TMP" && mv "$TMP" "$STATE_FILE"
}
if command -v flock >/dev/null 2>&1; then
  ( flock 9; _write_state ) 9>"$BASE/runtime/.waistate.lock"
else
  _write_state
fi
fi

# ── Tool Advisor: cheap stale marker ────────────────────────────────────────
if [[ -f "$PROJECT_DIR/tools/tool_advisor.py" ]]; then
  python3 "$PROJECT_DIR/tools/tool_advisor.py" --root "$PROJECT_DIR" --mark-stale-if-needed --session-id "$SESSION_NAME" >/dev/null 2>&1 || true
fi

# ── 3. Lug scan ──────────────────────────────────────────────────────────────
LUGS_DIR="$BASE/lugs/bytype"

count_lugs() {
  local pattern="$1"
  ls $pattern 2>/dev/null | wc -l | tr -d ' '
}

EPICS_OPEN=$(count_lugs "$LUGS_DIR/epic/open/*.json")
EPICS_IP=$(count_lugs "$LUGS_DIR/epic/in_progress/*.json")
TASKS_OPEN=$(count_lugs "$LUGS_DIR/task/open/*.json")
BUGS_IP=$(count_lugs "$LUGS_DIR/bug/in_progress/*.json")
FEATURES_IP=$(count_lugs "$LUGS_DIR/feature/in_progress/*.json")
OTHER_OPEN=$(count_lugs "$LUGS_DIR/other/open/*.json")
SIGNALS=$(count_lugs "$LUGS_DIR/signal/undelivered/*.json")

# Get epic names (open + in_progress)
EPIC_LIST=$(ls "$LUGS_DIR/epic/open/"*.json "$LUGS_DIR/epic/in_progress/"*.json 2>/dev/null \
  | xargs -I{} basename {} .json 2>/dev/null | sort | head -15 | sed 's/^/  - /' | tr '\n' '\n')

# Get in-progress lug names (non-epic)
IP_LIST=$(ls "$LUGS_DIR/bug/in_progress/"*.json "$LUGS_DIR/feature/in_progress/"*.json 2>/dev/null \
  | xargs -I{} basename {} .json 2>/dev/null | sort | sed 's/^/  - /' | tr '\n' '\n')

# ── 4. Hub + teaching check ───────────────────────────────────────────────────
HUB_PATH=$(jq -r '.wheel.hub_path // ""' "$STATE_FILE" 2>/dev/null)
NODE_TYPE=$(jq -r '.wheel.node_type // "spoke"' "$STATE_FILE" 2>/dev/null || echo "spoke")
PROCESSED_DIR="$BASE/seed/ingest/processed"

# Spoke nodes read spoke/current + cross_spoke/current; hub nodes read hub-only/current + cross_spoke/current
if [[ "$NODE_TYPE" == "hub" ]]; then
  TEACH_DIRS=("$HUB_PATH/teachings_repo/hub-only/current" "$HUB_PATH/teachings_repo/cross_spoke/current")
else
  TEACH_DIRS=("$HUB_PATH/teachings_repo/spoke/current" "$HUB_PATH/teachings_repo/cross_spoke/current")
fi

HUB_STATUS="MISSING"
TEACH_STATUS="MISSING"
TEACH_TOTAL=0
TEACH_ADOPTED=0
TEACH_NEW=0
TEACH_BASELINE=0
NEW_TEACHINGS=""

# Read the version this spoke was initialized at (absent on pre-filter spokes → "0.0.0" = see all)
INIT_VERSION=$(jq -r '.wheel.initialized_at_version // "0.0.0"' "$STATE_FILE" 2>/dev/null || echo "0.0.0")

# Returns true if $1 <= $2 (semver-safe via sort -V)
_version_lte() { [ "$(printf '%s\n' "$1" "$2" | sort -V | head -1)" = "$1" ]; }

if [[ -n "$HUB_PATH" && -d "$HUB_PATH" ]]; then
  HUB_STATUS="OK"
  TEACH_STATUS="OK"
  for TEACH_DIR in "${TEACH_DIRS[@]}"; do
    [[ -d "$TEACH_DIR" ]] || continue
    for f in "$TEACH_DIR"/*.teaching; do
      [[ -f "$f" ]] || continue
      fname=$(basename "$f")
      # Version filter: teachings predating the spoke's baseline are already baked in
      if [[ "$INIT_VERSION" != "0.0.0" ]]; then
        SINCE=$(grep -m1 '^since_version:' "$f" 2>/dev/null | awk '{print $2}' | tr -d '"')
        SINCE="${SINCE:-0.0.0}"
        if _version_lte "$SINCE" "$INIT_VERSION"; then
          TEACH_BASELINE=$((TEACH_BASELINE + 1))
          continue
        fi
      fi
      TEACH_TOTAL=$((TEACH_TOTAL + 1))
      if [[ -f "$PROCESSED_DIR/$fname" ]]; then
        TEACH_ADOPTED=$((TEACH_ADOPTED + 1))
      else
        TEACH_NEW=$((TEACH_NEW + 1))
        NEW_TEACHINGS="$NEW_TEACHINGS\n  - $fname"
        AUTO=$(grep -m1 'safe_to_auto_adopt' "$f" 2>/dev/null | grep -c 'true')
        if [[ "$AUTO" -eq 1 ]]; then
          NEW_TEACHINGS="$NEW_TEACHINGS [auto-adoptable]"
        else
          NEW_TEACHINGS="$NEW_TEACHINGS [manual review]"
        fi
      fi
    done
  done
fi

# ── 4b. Direct-delivery teachings (ingest/manual/ + ingest/incoming/) ─────────
# These arrive from spoke-to-spoke delivery (not via hub teachings_repo).
# Count pending ones that haven't been processed yet.
DIRECT_TEACH_NEW=0
DIRECT_TEACH_NAMES=''
for _dt_dir in "$BASE/seed/ingest/manual" "$BASE/seed/ingest/incoming"; do
  [[ -d "$_dt_dir" ]] || continue
  for _dtf in "$_dt_dir"/*.teaching; do
    [[ -f "$_dtf" ]] || continue
    _dtfname=$(basename "$_dtf")
    [[ -f "$PROCESSED_DIR/$_dtfname" ]] && continue
    DIRECT_TEACH_NEW=$((DIRECT_TEACH_NEW + 1))
    _dt_source=$(grep -m1 '^source_spoke:' "$_dtf" 2>/dev/null | awk '{print $2}' || echo '?')
    DIRECT_TEACH_NAMES="$DIRECT_TEACH_NAMES\n  - $_dtfname [from: $_dt_source, manual review]"
  done
done
[[ $DIRECT_TEACH_NEW -gt 0 ]] && TEACH_NEW=$((TEACH_NEW + DIRECT_TEACH_NEW)) && NEW_TEACHINGS="$NEW_TEACHINGS$DIRECT_TEACH_NAMES"

# ── 5. Hub signals bulletin count ────────────────────────────────────────────
# Count only framework-targeted signals (incoming/framework/) — hub/ signals are hub-session scope
HUB_SIGNALS=0
HUB_SIGNALS_HUB=0
if [[ -d "$HUB_PATH/WAI-Hub/signals/incoming" ]]; then
  # framework-targeted signals (exclude status=delivered — already absorbed)
  if [[ -d "$HUB_PATH/WAI-Hub/signals/incoming/framework" ]]; then
    HUB_SIGNALS=$(python3 -c "
import json, glob, os, sys
count = 0
for f in sorted(glob.glob(sys.argv[1] + '/*.json')):
    if os.path.basename(f) == '.gitkeep':
        continue
    try:
        d = json.load(open(f))
        if d.get('status') != 'delivered':
            count += 1
    except Exception:
        count += 1
print(count)
" "$HUB_PATH/WAI-Hub/signals/incoming/framework" 2>/dev/null || echo "0")
  else
    # fallback: flat incoming/ (pre-subfolder layout)
    HUB_SIGNALS=$(ls "$HUB_PATH/WAI-Hub/signals/incoming/"*.json 2>/dev/null | grep -v '.gitkeep' | wc -l | tr -d ' ')
  fi
  # hub-targeted signals (informational only — processed by hub sessions)
  if [[ -d "$HUB_PATH/WAI-Hub/signals/incoming/hub" ]]; then
    HUB_SIGNALS_HUB=$(ls "$HUB_PATH/WAI-Hub/signals/incoming/hub/"*.json 2>/dev/null | grep -v '.gitkeep' | wc -l | tr -d ' ')
  fi
fi

# ── 5b. Hub registry update ──────────────────────────────────────────────────
# Update outstanding_work counts in hub-registry.json on every session start.
# Match by path (not basename) — spoke directory name may differ from wheel_id.
if [[ "$HUB_STATUS" == "OK" && -f "$HUB_PATH/hub-registry.json" ]]; then
  WHEEL_ID=$(jq -r --arg path "$PROJECT_DIR" '.wheels[] | select(.path == $path) | .wheel_id' "$HUB_PATH/hub-registry.json" 2>/dev/null)
  if [[ -n "$WHEEL_ID" && "$WHEEL_ID" != "null" ]]; then
    _OPEN=$(count_lugs "$LUGS_DIR/*/open/*.json")
    _IP=$(count_lugs "$LUGS_DIR/*/in_progress/*.json")
    _TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    _TMP=$(mktemp)
    jq --arg id "$WHEEL_ID" \
       --argjson open "$_OPEN" \
       --argjson ip "$_IP" \
       --arg ts "$_TS" \
       '(.wheels[] | select(.wheel_id == $id)).outstanding_work = {"open": $open, "in_progress": $ip, "last_checked": $ts} |
        (.wheels[] | select(.wheel_id == $id)).last_sync = $ts' \
       "$HUB_PATH/hub-registry.json" > "$_TMP" 2>/dev/null \
      && mv "$_TMP" "$HUB_PATH/hub-registry.json" \
      || rm -f "$_TMP"
  fi
fi

# ── 6. Next session recommendation ───────────────────────────────────────────
NEXT_REC=$(jq -r '._session_state.next_session_recommendation // "None"' "$STATE_FILE" 2>/dev/null)
SESSION_COUNT=$(jq -r '._session_state.session_count // 0' "$STATE_FILE" 2>/dev/null)

# ── 7. Brief freshness pre-check (fast path gate) ───────────────────────────
# Compute now so all subsequent sections can skip heavy Python tools when fresh.
BRIEF_FRESH=false
_BRIEF_PATH="$BASE/wakeup-brief.json"
if [[ -f "$_BRIEF_PATH" ]]; then
  _CURRENT_SHA=$(git -C "$PROJECT_DIR" rev-parse HEAD 2>/dev/null || echo "")
  _BRIEF_SHA=$(jq -r '.git_sha_at_generation // ""' "$_BRIEF_PATH" 2>/dev/null || echo "")
  if [[ -n "$_CURRENT_SHA" && -n "$_BRIEF_SHA" && "$_CURRENT_SHA" == "$_BRIEF_SHA" ]]; then
    BRIEF_FRESH=true
  fi
fi

# ── 7a. Spoke integrity score + parity check ────────────────────────────────
INTEGRITY_SCORE=""
PARITY_STATUS=""
if [[ "$BRIEF_FRESH" == "true" ]]; then
  INTEGRITY_SCORE="  Integrity: (from brief — fast path)"
  PARITY_STATUS="  Parity: at head"
else
if [[ -f "$PROJECT_DIR/tools/spoke_integrity_score.py" ]]; then
  _SCORE=$(python3 "$PROJECT_DIR/tools/spoke_integrity_score.py" --quiet 2>/dev/null)
  if [[ -n "$_SCORE" ]]; then
    if [[ "$_SCORE" -ge 80 ]]; then
      INTEGRITY_SCORE="  Integrity: ${_SCORE}/100 [HEALTHY]"
    elif [[ "$_SCORE" -ge 50 ]]; then
      INTEGRITY_SCORE="  Integrity: ${_SCORE}/100 [DEGRADED]"
    else
      INTEGRITY_SCORE="  Integrity: ${_SCORE}/100 [CRITICAL]"
    fi
  fi
fi
if [[ -f "$PROJECT_DIR/tools/spoke_parity_check.py" ]]; then
  if python3 "$PROJECT_DIR/tools/spoke_parity_check.py" --quiet 2>/dev/null; then
    PARITY_STATUS="  Parity: at head"
  else
    PARITY_STATUS="  Parity: BEHIND HEAD — run spoke_parity_check.py"
  fi
fi
fi  # end BRIEF_FRESH else block for integrity/parity

# ── 7. Git status ─────────────────────────────────────────────────────────────
GIT_DIRTY=$(git -C "$PROJECT_DIR" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
GIT_STATUS="clean"
[[ "$GIT_DIRTY" -gt 0 ]] && GIT_STATUS="$GIT_DIRTY file(s) modified"

# ── 8. CC health check (claude-maximizer trigger) ────────────────────────────
CC_GAPS=""
SETTINGS_FILE="$PROJECT_DIR/.claude/settings.json"
CLAUDE_MD="$PROJECT_DIR/CLAUDE.md"

# Check deny rules
DENY_COUNT=$(jq '.permissions.deny // [] | length' "$SETTINGS_FILE" 2>/dev/null || echo 0)
[[ "$DENY_COUNT" -eq 0 ]] && CC_GAPS="${CC_GAPS}  - No deny rules in .claude/settings.json\n"

# Check CLAUDE.md weight
if [[ -f "$CLAUDE_MD" ]]; then
  CMD_LINES=$(wc -l < "$CLAUDE_MD" | tr -d ' ')
  [[ "$CMD_LINES" -lt 50 ]] && CC_GAPS="${CC_GAPS}  - CLAUDE.md underweight (${CMD_LINES} lines, ideal 50+)\n"
else
  CC_GAPS="${CC_GAPS}  - CLAUDE.md missing\n"
fi

# Check PreToolUse hook
HAS_PRETOOL=$(jq '.hooks.PreToolUse // empty' "$SETTINGS_FILE" 2>/dev/null)
[[ -z "$HAS_PRETOOL" ]] && CC_GAPS="${CC_GAPS}  - No PreToolUse guard hook configured\n"

# Check subagent definitions
AGENTS_DIR="$PROJECT_DIR/.claude/agents"
if [[ ! -d "$AGENTS_DIR" ]] || [[ -z "$(ls -A "$AGENTS_DIR" 2>/dev/null)" ]]; then
  CC_GAPS="${CC_GAPS}  - No subagent definitions in .claude/agents/\n"
fi

# ── 8b. Skill sync check ─────────────────────────────────────────────────────
SYNC_STATUS="OK"
TEMPLATES_CMDS="$PROJECT_DIR/templates/commands"
CLAUDE_CMDS="$PROJECT_DIR/.claude/commands"
if [[ -d "$TEMPLATES_CMDS" && -d "$CLAUDE_CMDS" ]]; then
  SYNC_OUT_OF_SYNC=""
  for src in "$TEMPLATES_CMDS"/wai*.md; do
    [[ -f "$src" ]] || continue
    fname=$(basename "$src")
    dst="$CLAUDE_CMDS/$fname"
    if [[ ! -f "$dst" ]]; then
      SYNC_OUT_OF_SYNC="$SYNC_OUT_OF_SYNC $fname"
    else
      src_md5=$(md5sum "$src" | cut -d' ' -f1)
      dst_md5=$(md5sum "$dst" | cut -d' ' -f1)
      [[ "$src_md5" != "$dst_md5" ]] && SYNC_OUT_OF_SYNC="$SYNC_OUT_OF_SYNC $fname"
    fi
  done
  [[ -n "$SYNC_OUT_OF_SYNC" ]] && SYNC_STATUS="⚠ out of sync:$SYNC_OUT_OF_SYNC — run /shipit"
fi

# ── 9. Historian advice (latest review) ──────────────────────────────────────
HISTORIAN_ADVICE=""
HISTORIAN_DIR="$BASE/advisors/historian/reviews"
if [[ -d "$HISTORIAN_DIR" ]]; then
  LATEST_REVIEW=$(ls -1 "$HISTORIAN_DIR"/review-*.md 2>/dev/null | sort | tail -1)
  if [[ -n "$LATEST_REVIEW" ]]; then
    # Extract "Advice for Next Session" section
    ADVICE=$(sed -n '/^## Advice for Next Session/,/^## /{ /^## Advice/d; /^## /d; p; }' "$LATEST_REVIEW" 2>/dev/null | head -10)
    if [[ -n "$ADVICE" ]]; then
      REVIEW_DATE=$(basename "$LATEST_REVIEW" .md | sed 's/review-//')
      HISTORIAN_ADVICE="  Historian ($REVIEW_DATE):\n$(echo "$ADVICE" | sed 's/^/    /')"
    fi
  fi
fi

# ── 9b. Expediter summary ────────────────────────────────────────────────────
EXPEDITER_SUMMARY=""
EXPEDITER_STATE="$BASE/advisors/expediter/scan_state.json"
if [[ "$BRIEF_FRESH" == "true" ]]; then
  # Fast path: use pre-computed queue data from brief instead of re-running expediter
  _READY=$(jq -r '.queue_snapshot.ready_count // 0' "$_BRIEF_PATH" 2>/dev/null || echo "0")
  _REFINE=$(jq -r '.queue_snapshot.needs_refinement_count // 0' "$_BRIEF_PATH" 2>/dev/null || echo "0")
  EXPEDITER_SUMMARY="  Expediter: (from brief) queue ${_READY} ready | ${_REFINE} need refinement"
else
if [[ -f "$PROJECT_DIR/tools/spoke_expediter.py" ]]; then
  python3 "$PROJECT_DIR/tools/spoke_expediter.py" --spoke-path "$PROJECT_DIR" >/dev/null 2>&1 || true
fi
if [[ -f "$EXPEDITER_STATE" ]]; then
  EXP_AVG=$(jq -r '.stats.last_quality_avg // "?"' "$EXPEDITER_STATE" 2>/dev/null)
  EXP_QUEUE=$(jq -r '.refinement_queue_size // 0' "$EXPEDITER_STATE" 2>/dev/null)
  EXP_RUN=$(jq -r '.last_run_at // ""' "$EXPEDITER_STATE" 2>/dev/null | cut -c1-10)
  EXPEDITER_SUMMARY="  Expediter: avg ${EXP_AVG}/10 | ${EXP_QUEUE} need refinement | last ${EXP_RUN}"
fi
fi  # end BRIEF_FRESH else block for expediter

# ── 9c. Advisor context feed staleness check ─────────────────────────────────
CONTEXT_FEED_STATUS=""
ADVISORS_DIR="$BASE/advisors"
if [[ -d "$ADVISORS_DIR" && -f "$PROJECT_DIR/tools/advisor_context_refresh.py" ]]; then
  STALE_ADVISORS=""
  UNINIT_ADVISORS=""
  NOW_TS=$(date +%s)

  for advisor_dir in "$ADVISORS_DIR"/*/; do
    [[ -f "${advisor_dir}feeds.yaml" ]] || continue
    advisor=$(basename "$advisor_dir")
    context_dir="${advisor_dir}context"

    # Get refresh interval (default 7 days)
    interval=$(python3 -c "
import sys, yaml
try:
    d = yaml.safe_load(open('${advisor_dir}feeds.yaml'))
    print(d.get('refresh_interval_days', 7))
except: print(7)
" 2>/dev/null || echo 7)

    # Find most recent snapshot
    if [[ -d "$context_dir" ]]; then
      latest_snap=$(ls -1t "$context_dir"/snapshot-*.md 2>/dev/null | head -1)
    else
      latest_snap=""
    fi

    if [[ -z "$latest_snap" ]]; then
      UNINIT_ADVISORS="$UNINIT_ADVISORS $advisor"
    else
      snap_ts=$(date -r "$latest_snap" +%s 2>/dev/null || echo 0)
      age_days=$(( (NOW_TS - snap_ts) / 86400 ))
      if [[ "$age_days" -gt "$interval" ]]; then
        STALE_ADVISORS="$STALE_ADVISORS ${advisor}[${age_days}d]"
      fi
    fi
  done

  # Auto-init uninit advisors in background
  if [[ -n "$UNINIT_ADVISORS" ]]; then
    mkdir -p "$HOME/.claude/logs"
    python3 "$PROJECT_DIR/tools/advisor_context_refresh.py" \
      --init --quiet --spoke-path "$PROJECT_DIR" \
      >> "$HOME/.claude/logs/context-refresh-$(date +%Y%m%d).log" 2>&1 &
    UNINIT_COUNT=$(echo $UNINIT_ADVISORS | wc -w | tr -d ' ')
    CONTEXT_FEED_STATUS="  Context feeds: ${UNINIT_COUNT} initializing in background (${UNINIT_ADVISORS# })"
  elif [[ -n "$STALE_ADVISORS" ]]; then
    STALE_COUNT=$(echo $STALE_ADVISORS | wc -w | tr -d ' ')
    CONTEXT_FEED_STATUS="  Context feeds: ${STALE_COUNT} stale — run: python3 tools/advisor_context_refresh.py"
  fi
fi

# ── 9b. Wakeup brief freshness check ───────────────────────────────────────
# Note: BRIEF_FRESH/_BRIEF_PATH/_CURRENT_SHA/_BRIEF_SHA already set in section 7 above.
WAKEUP_BRIEF_STATUS=""
WAKEUP_BRIEF_PATH="$_BRIEF_PATH"
if [[ -f "$WAKEUP_BRIEF_PATH" ]]; then
  if [[ "$BRIEF_FRESH" == "true" ]]; then
    MODE=$(jq -r '.generation_mode // "standard"' "$WAKEUP_BRIEF_PATH" 2>/dev/null || echo "standard")
    CHAIN_ID=$(jq -r '.chain_target_lug.id // ""' "$WAKEUP_BRIEF_PATH" 2>/dev/null || echo "")
    if [[ -n "$CHAIN_ID" ]]; then
      CHAIN_TITLE=$(jq -r '.chain_target_lug.title // ""' "$WAKEUP_BRIEF_PATH" 2>/dev/null | cut -c1-60)
      WAKEUP_BRIEF_STATUS="  Wakeup brief: FRESH (fast path — chained → ${CHAIN_ID}: ${CHAIN_TITLE})"
    else
      WAKEUP_BRIEF_STATUS="  Wakeup brief: FRESH (fast path — integrity/expediter/schedule skipped)"
    fi
  else
    WAKEUP_BRIEF_STATUS="  Wakeup brief: STALE (new commits since generation)"
  fi
fi

# ── 9b+. Savepoint pending check ───────────────────────────────────────────
SAVEPOINT_STATUS=""
if [[ -f "$STATE_FILE" ]]; then
  SP_INFO=$(python3 -c "
import json, glob
try:
    s = json.load(open('$STATE_FILE'))
    sp = s.get('_savepoint') or {}
    if sp.get('status') == 'pending':
        lug_id = sp.get('lug_id', '')
        title = ''
        lug_files = glob.glob('$BASE/lugs/bytype/*/in_progress/' + lug_id + '.json')
        if lug_files:
            lug_data = json.load(open(lug_files[0]))
            raw_title = lug_data.get('title', '')
            title = raw_title.split(' — ')[0].split(' -- ')[0][:60]
        print(lug_id)
        print(title)
        print(sp.get('resume_note', '')[:100])
except Exception:
    pass
" 2>/dev/null)
  if [[ -n "$SP_INFO" ]]; then
    SP_LUG=$(echo "$SP_INFO" | sed -n '1p')
    SP_TITLE=$(echo "$SP_INFO" | sed -n '2p')
    SP_NOTE=$(echo "$SP_INFO" | sed -n '3p')
    if [[ -n "$SP_LUG" ]]; then
      if [[ -n "$SP_TITLE" ]]; then
        SAVEPOINT_STATUS="  Savepoint: PENDING \"${SP_TITLE}\" — ${SP_NOTE}"
      else
        SAVEPOINT_STATUS="  Savepoint: PENDING [${SP_LUG}] — ${SP_NOTE}"
      fi
    fi
  fi
fi

# ── 9b++. Stale in_progress lug warning ────────────────────────────────────
STALE_LUGS_STATUS=""
STALE_COUNT=$(python3 -c "
import json, datetime, glob
from pathlib import Path
now = datetime.datetime.now(datetime.timezone.utc)
cutoff_hours = 4
stale = []
for f in glob.glob('$BASE/lugs/bytype/*/in_progress/*.json'):
    try:
        d = json.load(open(f))
        ts = d.get('updated_at') or d.get('created_at') or ''
        if not ts: continue
        dt = datetime.datetime.fromisoformat(ts.replace('Z', '+00:00'))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=datetime.timezone.utc)
        age_h = (now - dt).total_seconds() / 3600
        if age_h > cutoff_hours:
            stale.append((d.get('id', Path(f).stem), int(age_h)))
    except Exception:
        continue
stale.sort(key=lambda x: -x[1])
if stale:
    head = ', '.join(f'{sid}({ah}h)' for sid, ah in stale[:3])
    more = f' +{len(stale)-3}' if len(stale) > 3 else ''
    print(f'{len(stale)}|{head}{more}')
" 2>/dev/null)
if [[ -n "$STALE_COUNT" ]]; then
  _N=$(echo "$STALE_COUNT" | cut -d'|' -f1)
  _LIST=$(echo "$STALE_COUNT" | cut -d'|' -f2-)
  STALE_LUGS_STATUS="  Stale in_progress: ${_N} lug(s) unchanged >4h — ${_LIST}"
fi

# ── 9c. Advisor schedule evaluation ────────────────────────────────────────
ADVISORS_READY=""
if [[ "$BRIEF_FRESH" != "true" ]]; then
if [[ -f "$PROJECT_DIR/tools/advisor_schedule_eval.py" && -f "$BASE/advisors/schedule-index.json" ]]; then
  EVAL_OUT=$(cd "$PROJECT_DIR" && python3 tools/advisor_schedule_eval.py --json 2>/dev/null)
  if [[ -n "$EVAL_OUT" ]]; then
    ADVISORS_READY=$(python3 -c "
import json, sys
results = json.loads('$EVAL_OUT'.replace(\"'\", '\"') if False else sys.stdin.read())
ready = [r['advisor_id'] for r in results if r.get('should_fire')]
if ready:
    print('  Advisors ready to fire: ' + ', '.join(ready))
" <<< "$EVAL_OUT" 2>/dev/null || true)
  fi
fi
fi  # end BRIEF_FRESH guard for advisor schedule eval

# ── 10. Ozi nightly report (if hub connected) ───────────────────────────────
OZI_NIGHTLY=""
if [[ -n "$HUB_PATH" && -d "$HUB_PATH/WAI-Hub/runtime/ozi-nightly-reports" ]]; then
  # Find most recent report (today or yesterday)
  TODAY=$(date +%Y-%m-%d)
  YESTERDAY=$(date -d "yesterday" +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d 2>/dev/null || echo "")
  REPORT_FILE=""
  [[ -f "$HUB_PATH/WAI-Hub/runtime/ozi-nightly-reports/$TODAY.json" ]] && REPORT_FILE="$HUB_PATH/WAI-Hub/runtime/ozi-nightly-reports/$TODAY.json"
  [[ -z "$REPORT_FILE" && -n "$YESTERDAY" && -f "$HUB_PATH/WAI-Hub/runtime/ozi-nightly-reports/$YESTERDAY.json" ]] && REPORT_FILE="$HUB_PATH/WAI-Hub/runtime/ozi-nightly-reports/$YESTERDAY.json"

  if [[ -n "$REPORT_FILE" ]]; then
    REPORT_DATE=$(jq -r '.date // "unknown"' "$REPORT_FILE" 2>/dev/null)
    FLEET_SCANNED=$(jq -r '.spokes_scanned // 0' "$REPORT_FILE" 2>/dev/null)
    FLEET_GREEN=$(jq -r '.spokes_green // 0' "$REPORT_FILE" 2>/dev/null)
    FLEET_RED=$(jq -r '.spokes_red // 0' "$REPORT_FILE" 2>/dev/null)
    ITEMS_DONE=$(jq -r '.total_items_completed // 0' "$REPORT_FILE" 2>/dev/null)
    ITEMS_FAIL=$(jq -r '.total_items_failed // 0' "$REPORT_FILE" 2>/dev/null)
    TEACHINGS_ADOPTED=$(jq -r '.teachings_adopted // 0' "$REPORT_FILE" 2>/dev/null)

    # This spoke's results
    SPOKE_NAME=$(jq -r '.wheel.name // ""' "$STATE_FILE" 2>/dev/null)
    SPOKE_ITEMS=$(jq -r --arg name "$SPOKE_NAME" '.per_spoke[]? | select(.name == $name) | "\(.items_completed // 0) completed, \(.items_failed // 0) failed"' "$REPORT_FILE" 2>/dev/null)
    [[ -z "$SPOKE_ITEMS" ]] && SPOKE_ITEMS="not included in run"

    OZI_NIGHTLY="  Ozi nightly ($REPORT_DATE): fleet ${FLEET_GREEN}/${FLEET_SCANNED} green"
    [[ "$FLEET_RED" -gt 0 ]] && OZI_NIGHTLY="$OZI_NIGHTLY, ${FLEET_RED} red"
    OZI_NIGHTLY="$OZI_NIGHTLY | ${ITEMS_DONE} items done"
    [[ "$ITEMS_FAIL" -gt 0 ]] && OZI_NIGHTLY="$OZI_NIGHTLY, ${ITEMS_FAIL} failed"
    OZI_NIGHTLY="$OZI_NIGHTLY | teachings: ${TEACHINGS_ADOPTED}"
    OZI_NIGHTLY="$OZI_NIGHTLY\n  This spoke: ${SPOKE_ITEMS}"
  fi
fi

# ── Tool Advisor: surface pending config drift ──────────────────────────────
TOOL_ADVISOR_PENDING=""
TOOL_ADVISOR_STATE="$BASE/advisors/tool-advisor/scan_state.json"
if [[ -f "$TOOL_ADVISOR_STATE" ]]; then
  AUDIT_PENDING=$(jq -r '.audit_pending // false' "$TOOL_ADVISOR_STATE" 2>/dev/null)
  AUDIT_REASON=$(jq -r '.audit_reason // ""' "$TOOL_ADVISOR_STATE" 2>/dev/null)
  PENDING_PROPOSALS=$(jq -r '.pending_proposals | length' "$TOOL_ADVISOR_STATE" 2>/dev/null || echo 0)
  LAST_FINDING=$(jq -r '.last_findings[0] // ""' "$TOOL_ADVISOR_STATE" 2>/dev/null)

  [[ "$AUDIT_PENDING" == "true" ]] && TOOL_ADVISOR_PENDING="  ⚠ Tool audit due — ${AUDIT_REASON:-run /wai-tool-advisor}"
  [[ "$PENDING_PROPOSALS" -gt 0 ]] && TOOL_ADVISOR_PENDING="${TOOL_ADVISOR_PENDING}\n  ⚠ Tool Advisor: ${PENDING_PROPOSALS} proposal(s) pending review"
  [[ -n "$LAST_FINDING" ]] && TOOL_ADVISOR_PENDING="${TOOL_ADVISOR_PENDING}\n  ⚠ Last finding: ${LAST_FINDING}"
fi

# ── Concurrency banner: another live session shares this working tree ────────
# Lanes isolate per-turn TRACKING, but all sessions share ONE git working tree — so
# the residual hazard is git staging (one session's `git add -A` sweeping another's
# in-flight files, the S45 silent-revert). Surface the live peers + commit-safety
# advice so this session scopes its adds.
CONCURRENCY_BLOCK=""
if [[ "${LANE_OTHERS_COUNT:-0}" -gt 0 && -n "$CC_SID" && -f "$_WG" ]]; then
  _OWN_ADVICE=$(python3 "$_WG" ownership --session "$CC_SID" --base "$BASE" --repo-path "$PROJECT_DIR" 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('advice',''))" 2>/dev/null)
  CONCURRENCY_BLOCK="CONCURRENT SESSIONS\n  ⚠ ${LANE_OTHERS_COUNT} other live session(s) sharing this working tree.\n  Your track is isolated: ${BASE_REL}/sessions/${SESSION_NAME}/track.jsonl\n  Commit safety: ${_OWN_ADVICE:-scope every git add to your own files; do not git add -A.}\n  Source isolation: launch a session in its own worktree — python3 WAI-Harness/spoke/managed/tools/worktree_guard.py wt-new <name>, then 'cd .worktrees/<name> && claude'."
fi

# ── Static data for fast-path briefing (zero tool calls in wai skill) ────────
PROJECT_NAME=$(jq -r '.wheel.name // "Wheelwright"' "$STATE_FILE" 2>/dev/null || echo "Wheelwright")
PROJECT_VERSION=$(jq -r '.wheel.version // "?"' "$STATE_FILE" 2>/dev/null || echo "?")
SKILLS_COUNT=$(wc -l < "$BASE/skills/WAI-Skills.jsonl" 2>/dev/null | tr -d ' ' || echo 0)
WAISTATE_GIT=$(git -C "$PROJECT_DIR" status --short "$BASE_REL/WAI-State.json" 2>/dev/null | head -1 | awk '{print $1}' | xargs 2>/dev/null || echo "clean")
CUSTOM_FILES=$(ls "$PROJECT_DIR"/*.md 2>/dev/null | grep -viE "/(README|CLAUDE|GEMINI|AGENTS|CHANGELOG)" | xargs -I{} basename {} 2>/dev/null | tr '\n' ' ' | xargs 2>/dev/null || echo "none")

# ── Output ────────────────────────────────────────────────────────────────────
cat << BRIEF
<wai-session-init>
Session ${SESSION_COUNT} initialized. Track: ${BASE_REL}/sessions/${SESSION_NAME}/track.jsonl
$(if [[ -n "$CONCURRENCY_BLOCK" ]]; then printf "\n%b\n" "$CONCURRENCY_BLOCK"; fi)
ACTIVE WORK
  Epics: ${EPICS_OPEN} open, ${EPICS_IP} in-progress
  Tasks: ${TASKS_OPEN} open | Bugs/Features in-progress: $((BUGS_IP + FEATURES_IP))
  Other open: ${OTHER_OPEN} | Signals undelivered: ${SIGNALS}

EPICS
${EPIC_LIST}
IN-PROGRESS (non-epic)
${IP_LIST}
TEACHINGS
  Hub: ${HUB_STATUS} | Teachings repo: ${TEACH_STATUS}
  Total: ${TEACH_TOTAL} | Adopted: ${TEACH_ADOPTED} | New: ${TEACH_NEW}$(if [[ $TEACH_BASELINE -gt 0 ]]; then printf " | Baseline (skipped): %s" "$TEACH_BASELINE"; fi)
$(if [[ $TEACH_NEW -gt 0 ]]; then printf "  New teachings:\n%b" "$NEW_TEACHINGS"; fi)

HUB SIGNALS INBOX: ${HUB_SIGNALS} framework items$(if [[ $HUB_SIGNALS_HUB -gt 0 ]]; then printf " | %s hub-only (hub session scope)" "$HUB_SIGNALS_HUB"; fi)

$(if [[ -n "$OZI_NIGHTLY" ]]; then printf "OZI NIGHTLY\n%b\n" "$OZI_NIGHTLY"; fi)
$(if [[ -n "$HISTORIAN_ADVICE" ]]; then printf "HISTORIAN ADVICE\n%b\n" "$HISTORIAN_ADVICE"; fi)
CONTEXT HEALTH
  Git: ${GIT_STATUS}
  Hub path: ${HUB_STATUS}
  Prev session: ${PREV_SESSION_STATUS}$(if [[ -n "$PREV_SESSION_ID" ]]; then echo " (${PREV_SESSION_ID})"; fi)$(if [[ "$PREV_SESSION_STATUS" == "INTERRUPTED" ]]; then echo " ⚠ recovery prompt shown pre-launch"; fi)
$(if [[ -n "$INTEGRITY_SCORE" ]]; then echo "$INTEGRITY_SCORE"; fi)
$(if [[ -n "$PARITY_STATUS" ]]; then echo "$PARITY_STATUS"; fi)
$(if [[ -n "$WAKEUP_BRIEF_STATUS" ]]; then echo "$WAKEUP_BRIEF_STATUS"; fi)
$(if [[ -n "$SAVEPOINT_STATUS" ]]; then echo "$SAVEPOINT_STATUS"; fi)
$(if [[ -n "$STALE_LUGS_STATUS" ]]; then echo "$STALE_LUGS_STATUS"; fi)
$(if [[ $SIGNALS_APPLIED_COUNT -gt 0 ]]; then printf "  Signals: Applied %d patch(es):%b\n" "$SIGNALS_APPLIED_COUNT" "$SIGNALS_APPLIED_PATCHES"; fi)
  Sync: ${SYNC_STATUS}
$(if [[ -n "$EXPEDITER_SUMMARY" ]]; then echo "$EXPEDITER_SUMMARY"; fi)
$(if [[ -n "$CONTEXT_FEED_STATUS" ]]; then echo "$CONTEXT_FEED_STATUS"; fi)
$(if [[ -n "$ADVISORS_READY" ]]; then echo "$ADVISORS_READY"; fi)
$(if [[ -n "$CC_GAPS" ]]; then printf "\nCLAUDE OPTIMIZATION (run /wai-tool-advisor for details)\n%b" "$CC_GAPS"; fi)
NEXT ACTIONS (from session $((SESSION_COUNT - 1)))
  ${NEXT_REC}
$(if [[ -n "$TOOL_ADVISOR_PENDING" ]]; then printf "\nTOOL ADVISOR\n%b\n" "$TOOL_ADVISOR_PENDING"; fi)
STATIC DATA
  Project: ${PROJECT_NAME} v${PROJECT_VERSION}
  Skills: ${SKILLS_COUNT}
  WAI-State git: ${WAISTATE_GIT:-clean}
  Custom files: ${CUSTOM_FILES:-none detected}
</wai-session-init>
BRIEF

# ── Pre-write track entry (eliminates tool call from /wai fast path) ────────
if [[ "$SKIP_SESSION_INIT" == "false" && -n "$SESSION_DIR" ]]; then
  _TRK_MODE="standard"
  [[ "$BRIEF_FRESH" == "true" ]] && _TRK_MODE="fast-path"
  python3 -c "
import json, datetime
entry = {'event': 'session_start', 'session_id': '${SESSION_NAME}', 'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'mode': '${_TRK_MODE}', 'wakeup': 'pre-computed'}
with open('${SESSION_DIR}/track.jsonl', 'a') as f:
    f.write(json.dumps(entry) + chr(10))
" 2>/dev/null || true
fi

exit 0
