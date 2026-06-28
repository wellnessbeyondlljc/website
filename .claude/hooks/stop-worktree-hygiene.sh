#!/bin/bash
# stop-worktree-hygiene.sh — Warn when agent worktrees are left dirty+uncommitted.
# (impl-basher-fleet-hygiene-routine-v1)
#
# Runs on every Stop event (every turn). Lightweight: uses `git worktree list`
# and `git status --porcelain`. Silent if all worktrees are clean. Surfaces a
# systemMessage warning if any agent worktrees are dirty and 0 commits ahead of
# main (the exact condition that creates stranded, loss-prone worktrees).
#
# Writes a breadcrumb to .claude/hooks/worktree-hygiene.log for diagnostics.
# Always exits 0 — never blocks the session.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG="$PROJECT_DIR/.claude/hooks/worktree-hygiene.log"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

emit_warning() {
  _WHG_MSG="$1" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
print(json.dumps({"systemMessage": os.environ.get("_WHG_MSG", "")}))
PYEOF
}

# List all worktrees; filter for agent-* entries
STRANDED=()
while IFS= read -r line; do
  if [[ "$line" == worktree\ * ]]; then
    WP="${line#worktree }"
    # Only check .claude/worktrees/agent-* paths
    if [[ "$WP" == *"/.claude/worktrees/agent-"* ]] && [[ -d "$WP" ]]; then
      # Check dirty files
      DIRTY_COUNT=$(git -C "$WP" status --porcelain 2>/dev/null | grep -c .)
      if [[ "$DIRTY_COUNT" -gt 0 ]]; then
        # Check commits ahead of main (0 = not yet committed to its own branch)
        BR=$(git -C "$WP" branch --show-current 2>/dev/null || echo "")
        if [[ -n "$BR" ]]; then
          AHEAD=$(git -C "$PROJECT_DIR" rev-list --count "main..$BR" 2>/dev/null || echo "?")
        else
          AHEAD="0"
        fi
        if [[ "$AHEAD" == "0" || "$AHEAD" == "?" ]]; then
          STRANDED+=("$WP ($DIRTY_COUNT dirty files, branch=$BR)")
        fi
      fi
    fi
  fi
done < <(git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null)

if [[ ${#STRANDED[@]} -gt 0 ]]; then
  MSG="⚠️ ${#STRANDED[@]} stranded agent worktree(s) detected with uncommitted changes (at risk of loss on prune):"
  for S in "${STRANDED[@]}"; do
    MSG="$MSG
  $S"
  done
  MSG="$MSG
Run: fleet_hygiene_scan.py fleet --registry <hub-registry.json> --rescue --out-dir <dir> to salvage."
  emit_warning "$MSG"
  printf '%s stranded_worktrees=%d\n' "$TS" "${#STRANDED[@]}" >> "$LOG" 2>/dev/null
fi

exit 0
