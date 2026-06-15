#!/usr/bin/env bash
# tools/closeout.sh — WAI Closeout Automation
#
# Handles mechanical closeout steps so the AI only does semantic work.
# Idempotent: safe to run multiple times on the same session.
#
# Usage:
#   tools/closeout.sh [--dry-run] [--modified-by MODEL_ID] [--track-path PATH]
#
# Steps:
#   1. Bump wheel.version patch
#   2. session_count++, last_closeout, last_modified_at/by
#   3. Archive in_progress lugs with status==completed
#   4. Regenerate WAI-LugIndex.jsonl
#   5. Score backlog + update _work_queue.items

set -euo pipefail

log()    { echo "  ✓ $1"; }
drylog() { echo "  ~ [DRY-RUN] $1"; }
header() { echo ""; echo "── $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRAMEWORK_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default to current directory if it looks like a WAI spoke
if [ -d "./WAI-Spoke" ] && [ -f "./WAI-Spoke/WAI-State.json" ]; then
    TARGET_SPOKE_ROOT="."
    log "Target: current directory spoke ($(pwd))"
else
    TARGET_SPOKE_ROOT="$FRAMEWORK_ROOT"
    log "Target: framework root spoke ($FRAMEWORK_ROOT)"
fi

WAI_STATE="$TARGET_SPOKE_ROOT/WAI-Spoke/WAI-State.json"
LUGS_DIR="$TARGET_SPOKE_ROOT/WAI-Spoke/lugs/bytype"
INDEX_FILE="$TARGET_SPOKE_ROOT/WAI-Spoke/WAI-LugIndex.jsonl"

DRY_RUN=false
MODIFIED_BY="closeout.sh"
TRACK_PATH=""

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        --modified-by) MODIFIED_BY="$2"; shift ;;
        --track-path) TRACK_PATH="$2"; shift ;;
        *) echo "Unknown flag: $1" >&2 ;;
    esac
    shift
done

log()    { echo "  ✓ $1"; }
drylog() { echo "  ~ [DRY-RUN] $1"; }
header() { echo ""; echo "── $1"; }

do_or_dry() {
    # do_or_dry "description" cmd args...
    local desc="$1"; shift
    if $DRY_RUN; then
        drylog "$desc"
    else
        "$@"
        log "$desc"
    fi
}

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   WAI Closeout Script                ║"
if $DRY_RUN; then
echo "║   Mode: DRY-RUN (no changes)         ║"
fi
echo "╚══════════════════════════════════════╝"

# Validate state file exists
if [ ! -f "$WAI_STATE" ]; then
    echo "ERROR: WAI-State.json not found at $WAI_STATE" >&2
    exit 1
fi

# ── Step 1: Version bump ────────────────────────────────────────────────────
header "Step 1: Version"

CURRENT_VERSION=$(jq -r '.wheel.version' "$WAI_STATE")
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"
NEW_PATCH=$((PATCH + 1))
NEW_VERSION="${MAJOR}.${MINOR}.${NEW_PATCH}"

if $DRY_RUN; then
    drylog "wheel.version: $CURRENT_VERSION → $NEW_VERSION"
else
    jq --arg v "$NEW_VERSION" '.wheel.version = $v' "$WAI_STATE" > "${WAI_STATE}.tmp"
    mv "${WAI_STATE}.tmp" "$WAI_STATE"
    log "wheel.version: $CURRENT_VERSION → $NEW_VERSION"
fi

# ── Step 2: Session count + timestamps ────────────────────────────────────
header "Step 2: Session state"

CURRENT_COUNT=$(jq -r '._session_state.session_count // 0' "$WAI_STATE")
NEW_COUNT=$((CURRENT_COUNT + 1))
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

if $DRY_RUN; then
    drylog "session_count: $CURRENT_COUNT → $NEW_COUNT"
    drylog "last_closeout / last_modified_at: $NOW"
    drylog "last_modified_by: $MODIFIED_BY"
else
    TRACK_UPDATE=""
    if [ -n "$TRACK_PATH" ]; then
        TRACK_UPDATE='| ._session_state.track_path = $track'
    fi

    jq --argjson count "$NEW_COUNT" \
       --arg now "$NOW" \
       --arg by "$MODIFIED_BY" \
       --arg track "$TRACK_PATH" \
       "._session_state.session_count = \$count |
        ._session_state.last_closeout = \$now |
        .wheel.last_modified_at = \$now |
        .wheel.last_modified_by = \$by |
        if \$track != \"\" then ._session_state.track_path = \$track else . end" \
       "$WAI_STATE" > "${WAI_STATE}.tmp"
    mv "${WAI_STATE}.tmp" "$WAI_STATE"
    log "session_count: $CURRENT_COUNT → $NEW_COUNT"
    log "last_closeout: $NOW"
    log "last_modified_by: $MODIFIED_BY"
fi

# ── Step 3: Lug archival ────────────────────────────────────────────────────
header "Step 3: Lug archival (in_progress → completed)"

MOVED=0
if [ -d "$LUGS_DIR" ]; then
    while IFS= read -r -d '' lug_file; do
        STATUS=$(jq -r '.status // .s // ""' "$lug_file" 2>/dev/null)
        if [[ "$STATUS" == "completed" || "$STATUS" == "c" || "$STATUS" == "closed" || "$STATUS" == "resolved" ]]; then
            TYPE_DIR="$(dirname "$(dirname "$lug_file")")"
            DEST="$TYPE_DIR/completed/$(basename "$lug_file")"
            if $DRY_RUN; then
                drylog "Move: $(basename "$lug_file") → completed/"
            else
                mkdir -p "$(dirname "$DEST")"
                mv "$lug_file" "$DEST"
                log "Moved: $(basename "$lug_file") → completed/"
            fi
            MOVED=$((MOVED + 1))
        fi
    done < <(find "$LUGS_DIR" -path "*/in_progress/*.json" -print0 2>/dev/null)
fi

if [ "$MOVED" -eq 0 ]; then
    log "No in_progress lugs ready for archival"
else
    log "Total moved: $MOVED lug(s)"
fi

# ── Step 3.5: Reconcile completed/ folder ↔ status field ───────────────────
# Catches drift: lugs in completed/ with non-terminal status (forgotten flips,
# manual mv, LLM drift). Verifies target_files when declared; demotes truly
# unfinished work back to open/ or in_progress/. Idempotent.
header "Step 3.5: Lug status reconcile"
if [ -x "$FRAMEWORK_ROOT/tools/lug_status_reconcile.py" ]; then
    if $DRY_RUN; then
        drylog "Would run: lug_status_reconcile.py --session $MODIFIED_BY"
        python3 "$FRAMEWORK_ROOT/tools/lug_status_reconcile.py" || true
    else
        python3 "$FRAMEWORK_ROOT/tools/lug_status_reconcile.py" \
            --apply --session "$MODIFIED_BY" || log "  ⚠ reconciler exited non-zero (continuing)"
    fi
else
    log "  (reconciler not present — skipping)"
fi

# ── Step 4: Regenerate WAI-LugIndex.jsonl ──────────────────────────────────
header "Step 4: Lug index regen"

if $DRY_RUN; then
    TOTAL_LUGS=$(find "$LUGS_DIR" -name "*.json" 2>/dev/null | wc -l)
    drylog "Would write $TOTAL_LUGS entries to WAI-LugIndex.jsonl"
else
    TEMP_INDEX="${INDEX_FILE}.tmp"
    : > "$TEMP_INDEX"
    TOTAL=0

    # Get absolute path of TARGET_SPOKE_ROOT for sed
    SPOKE_ABS="$(cd "$TARGET_SPOKE_ROOT" && pwd)"

    while IFS= read -r -d '' lug_file; do
        FOLDER="$(dirname "$lug_file" | sed "s|$SPOKE_ABS/||")"
        ID=$(jq -r '.id // .i // "unknown"' "$lug_file" 2>/dev/null || echo "unknown")
        TYPE=$(jq -r '.type // .ty // "unknown"' "$lug_file" 2>/dev/null || echo "unknown")
        STATUS=$(jq -r '.status // .s // "unknown"' "$lug_file" 2>/dev/null || echo "unknown")
        TITLE=$(jq -r '.title // .t // ""' "$lug_file" 2>/dev/null || echo "")
        CREATED=$(jq -r '.created_at // .ca // ""' "$lug_file" 2>/dev/null || echo "")
        ROUTED=$(jq -r '.routed_to // "LOCAL"' "$lug_file" 2>/dev/null || echo "LOCAL")

        printf '{"id":%s,"type":%s,"status":%s,"title":%s,"folder":%s,"created_at":%s,"routed_to":%s}\n' \
            "$(echo "$ID" | jq -Rs .)" \
            "$(echo "$TYPE" | jq -Rs .)" \
            "$(echo "$STATUS" | jq -Rs .)" \
            "$(echo "$TITLE" | jq -Rs .)" \
            "$(echo "$FOLDER" | jq -Rs .)" \
            "$(echo "$CREATED" | jq -Rs .)" \
            "$(echo "$ROUTED" | jq -Rs .)" \
            >> "$TEMP_INDEX"
        TOTAL=$((TOTAL + 1))
    done < <(find "$LUGS_DIR" -name "*.json" -print0 2>/dev/null | sort -z)

    mv "$TEMP_INDEX" "$INDEX_FILE"
    log "Index: $TOTAL entries written"
fi

# ── Step 5: Score backlog + update work queue ──────────────────────────────
header "Step 5: Backlog scoring"

SCORE_PY="$FRAMEWORK_ROOT/tools/score_backlog.py"
if [ -f "$SCORE_PY" ]; then
    if $DRY_RUN; then
        drylog "Would run score_backlog.py --update-state"
    else
        # Run from target spoke root so Python finds WAI-Spoke correctly
        cd "$TARGET_SPOKE_ROOT"
        SCORE_OUT=$(python3 "$SCORE_PY" --update-state 2>/dev/null || echo "")
        if [ -n "$SCORE_OUT" ]; then
            # Extract summary line
            SUMMARY=$(echo "$SCORE_OUT" | grep -E "ready|_work_queue updated" | tail -2 || echo "")
            log "Backlog scored"
            if [ -n "$SUMMARY" ]; then
                echo "$SUMMARY" | while IFS= read -r line; do echo "    $line"; done
            fi
        else
            log "Backlog scoring complete (empty output)"
        fi
    fi
else
    log "score_backlog.py not found — skipping"
fi

# ── Step 6: Regenerate llms-full.md ─────────────────────────────────────────
header "Step 6: Docs (llms-full.md)"

GEN_SCRIPT="$FRAMEWORK_ROOT/framework/docs/generate-llms-txt.sh"
if [ -f "$GEN_SCRIPT" ]; then
    if $DRY_RUN; then
        drylog "Would regenerate framework/docs/llms-full.md"
    else
        # generate-llms-txt.sh likely expects to run from framework root
        (cd "$FRAMEWORK_ROOT" && bash "$GEN_SCRIPT" 2>/dev/null) && \
            log "framework/docs/llms-full.md regenerated (v${NEW_VERSION})" || \
            log "llms-full.md regeneration failed — skipping (non-blocking)"
    fi
else
    log "generate-llms-txt.sh not found — skipping"
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Closeout Summary                   ║"
echo "╠══════════════════════════════════════╣"
printf "║  %-36s ║\n" "Version:  $CURRENT_VERSION → $NEW_VERSION"
printf "║  %-36s ║\n" "Sessions: $CURRENT_COUNT → $NEW_COUNT"
printf "║  %-36s ║\n" "Archived: $MOVED lug(s)"
if $DRY_RUN; then
echo "║  (no changes written — dry-run)      ║"
fi
echo "╚══════════════════════════════════════╝"
echo ""
echo "Remaining AI steps: signal extraction, next_session_recommendation, git commit."
echo ""
