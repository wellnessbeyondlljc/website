#!/usr/bin/env bash
# wai-chain.sh — Autonomous session-to-session work queue execution
#
# Usage:
#   ./tools/wai-chain.sh [--budget N] [--dry-run]
#
# Spawns Claude Code sessions that:
#   1. Wakeup (warm session)
#   2. Pick top ROI lug from score_backlog.py
#   3. Execute the lug
#   4. Closeout (tags next lug, reports to hub changelog)
#   5. Spawn new session → repeat
#
# Stops when:
#   - Work queue is empty (no items with ROI >= 3.0)
#   - Budget hit (--budget N sessions, default 5)
#   - Any session fails (non-zero exit)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUDGET=5
DRY_RUN=false
VIBE=""
CHAIN_LOG="$PROJECT_DIR/WAI-Spoke/runtime/chain-log.jsonl"

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --budget) BUDGET="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --vibe) VIBE="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

mkdir -p "$PROJECT_DIR/WAI-Spoke/runtime"

echo "╔══════════════════════════════════════════════╗"
echo "║  WAI Chain Mode — Autonomous Queue Runner    ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Budget: $BUDGET sessions                        ║"
echo "║  Vibe: ${VIBE:-auto}                              ║"
echo "║  Project: $(basename "$PROJECT_DIR")                      ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

SESSION_NUM=0

while [ "$SESSION_NUM" -lt "$BUDGET" ]; do
    SESSION_NUM=$((SESSION_NUM + 1))

    # Get top ROI item
    VIBE_ARG="${VIBE:-}"
    TOP_ITEM=$(cd "$PROJECT_DIR" && python3 tools/score_backlog.py $VIBE_ARG 2>/dev/null | \
        grep -E '^\s+[0-9]+\s+[0-9]' | head -1 | awk '{print $NF}' || true)

    # Get full line for ROI and type
    TOP_LINE=$(cd "$PROJECT_DIR" && python3 tools/score_backlog.py $VIBE_ARG 2>/dev/null | \
        grep -E '^\s+1\s+' | head -1 || true)

    TOP_ROI=$(echo "$TOP_LINE" | awk '{print $2}')
    TOP_TYPE=$(echo "$TOP_LINE" | awk '{print $3}')
    TOP_STATUS=$(echo "$TOP_LINE" | awk '{print $4}')

    # Find the actual lug file
    TOP_LUG_FILE=$(cd "$PROJECT_DIR" && find WAI-Spoke/lugs/bytype/ -name "*.json" -path "*/$TOP_STATUS/*" 2>/dev/null | head -1 || true)

    # Better: use the scorer to get the actual file (with gate checks)
    TOP_LUG_FILE=$(cd "$PROJECT_DIR" && python3 -c "
import json, sys
sys.path.insert(0, 'tools')
from score_backlog import scan_active_lugs, score_lug
from lug_utils import evaluate_execute_when, load_phases_from_state
lugs = scan_active_lugs()
phases = load_phases_from_state()
vibe = '$VIBE_ARG' or None
scored = []
for e in lugs:
    roi = score_lug(e['lug'], e['type'], e['status'], vibe)
    scored.append({**e, 'roi': roi})
scored.sort(key=lambda x: x['roi'], reverse=True)
# Skip signals and 'other' — only actionable types
# Also skip blocked/gated items
for item in scored:
    if item['type'] in ('task', 'bug', 'feature') and item['roi'] >= 3.0:
        ready, reason = evaluate_execute_when(item['lug'], phases)
        if not ready:
            continue
        print(f\"WAI-Spoke/lugs/bytype/{item['type']}/{item['status']}/{item['file']}\")
        break
" 2>/dev/null || true)

    if [ -z "$TOP_LUG_FILE" ]; then
        echo ""
        echo "═══ Queue empty (no actionable items with ROI >= 3.0) ═══"
        echo "Chain complete after $((SESSION_NUM - 1)) sessions."
        break
    fi

    TOP_LUG_ID=$(basename "$TOP_LUG_FILE" .json)
    TOP_LUG_TITLE=$(cd "$PROJECT_DIR" && python3 -c "
import json
lug = json.load(open('$TOP_LUG_FILE'))
print(lug.get('t', lug.get('title', '$TOP_LUG_ID'))[:70])
" 2>/dev/null || echo "$TOP_LUG_ID")

    echo ""
    echo "━━━ Chain Session $SESSION_NUM/$BUDGET ━━━"
    echo "  Lug: $TOP_LUG_ID"
    echo "  Title: $TOP_LUG_TITLE"
    echo "  File: $TOP_LUG_FILE"
    echo ""

    # Log chain entry
    echo "{\"session\": $SESSION_NUM, \"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"lug\": \"$TOP_LUG_ID\", \"title\": \"$TOP_LUG_TITLE\", \"status\": \"starting\"}" >> "$CHAIN_LOG"

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY RUN] Would execute: claude --print \"wai wakeup then execute lug $TOP_LUG_ID then /wai-closeout\""
        echo "{\"session\": $SESSION_NUM, \"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"lug\": \"$TOP_LUG_ID\", \"status\": \"dry_run_skip\"}" >> "$CHAIN_LOG"
        continue
    fi

    # Build the chain prompt
    CHAIN_PROMPT="You are in chain mode. Execute this sequence exactly:

1. Run wai wakeup (abbreviated — skip vibe prompt, skip teachings, just load state and active work counts)
2. Read and execute this lug: $TOP_LUG_FILE
   - Follow its PEV contract: perceive → execute → verify
   - Commit when the lug is complete (mark resolved, move to completed/)
3. Report progress: append to WAI-Spoke/runtime/spoke-changelog.jsonl:
   {\"ts\": \"ISO-8601\", \"lug\": \"$TOP_LUG_ID\", \"title\": \"$TOP_LUG_TITLE\", \"result\": \"completed|failed\", \"session\": \"session-ID\", \"commit\": \"hash\"}
4. Run /wai-closeout (standard ceremony)
   - In next_session_recommendation, write: \"Chain mode: next lug is [top ROI item from score_backlog.py]\"
5. Exit cleanly.

IMPORTANT: This is an automated chain run. Do not ask questions — make reasonable decisions. If the lug is blocked or unclear, mark it as blocked with a reason and move to the next one. Commit per milestone."

    # Spawn claude in non-interactive mode
    echo "  Spawning Claude Code session..."
    cd "$PROJECT_DIR"

    # Use claude with --print for non-interactive execution
    if claude --print "$CHAIN_PROMPT" > "WAI-Spoke/runtime/chain-session-$SESSION_NUM.log" 2>&1; then
        echo "  Session $SESSION_NUM completed successfully."
        echo "{\"session\": $SESSION_NUM, \"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"lug\": \"$TOP_LUG_ID\", \"status\": \"completed\"}" >> "$CHAIN_LOG"
    else
        EXIT_CODE=$?
        echo "  Session $SESSION_NUM failed (exit $EXIT_CODE). Stopping chain."
        echo "{\"session\": $SESSION_NUM, \"ts\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \"lug\": \"$TOP_LUG_ID\", \"status\": \"failed\", \"exit_code\": $EXIT_CODE}" >> "$CHAIN_LOG"
        break
    fi

    echo "  Waiting 3 seconds before next session..."
    sleep 3
done

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Chain Complete                               ║"
echo "║  Sessions run: $SESSION_NUM                          ║"
echo "║  Log: WAI-Spoke/runtime/chain-log.jsonl       ║"
echo "╚══════════════════════════════════════════════╝"
