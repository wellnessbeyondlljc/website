#!/bin/bash
#
# PreToolUse Guard — blocks destructive commands at hook level
# Returns JSON with decision: allow/deny/ask
# Stderr output blocks the action; stdout is informational
#

input=$(cat)
tool=$(echo "$input" | jq -r '.tool_name // ""')

# CSRP AC4 — lane heartbeat (initiative: csrp-intelligent-auto-reconciliation).
# Lanes were only stamped at SessionStart, so a live session older than the 12h TTL
# got reaped from the registry -> every concurrency guard then failed OPEN (blind).
# Refresh this lane's last_seen on tool use, throttled ~5min via a marker (cheap;
# fails silent; fires for ALL tools, before the Bash-only early-exit).
_hb_sid=$(echo "$input" | jq -r '.session_id // ""' 2>/dev/null)
_hb_base="${CLAUDE_PROJECT_DIR:-.}/WAI-Harness/spoke/local"
if [ -n "$_hb_sid" ] && [ -d "$_hb_base" ]; then
  _hb_mark="$_hb_base/runtime/lanes/$_hb_sid/.hb"
  if [ -z "$(find "$_hb_mark" -mmin -5 2>/dev/null)" ]; then
    _hb_wg="${CLAUDE_PROJECT_DIR:-.}/WAI-Harness/spoke/managed/tools/worktree_guard.py"
    [ -f "$_hb_wg" ] && python3 "$_hb_wg" lane-register --session "$_hb_sid" --base "$_hb_base" >/dev/null 2>&1 || true
    mkdir -p "$(dirname "$_hb_mark")" 2>/dev/null && touch "$_hb_mark" 2>/dev/null || true
  fi
fi

# Only guard Bash commands — exit 0 silently to allow (no stdout; stdout causes hook error messages)
[[ "$tool" != "Bash" ]] && exit 0

cmd=$(echo "$input" | jq -r '.tool_input.command // ""')

# Extract only executable lines (strip heredoc bodies and quoted strings)
# Take the first line and any lines not inside a heredoc
first_line=$(echo "$cmd" | head -1)

# Block: rm -rf / (root deletion) — only on first line to avoid heredoc false positives
if echo "$first_line" | grep -qE '^\s*\\?rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\s*$|^\s*\\?rm\s+-rf\s+/'; then
  echo "BLOCKED: rm -rf / — destructive root deletion" >&2
  exit 2
fi

# Block: force push — check full command but only as a standalone git command
if echo "$first_line" | grep -qE '^\s*git\s+push\s+(-f|--force)'; then
  echo "BLOCKED: git push --force — use regular push" >&2
  exit 2
fi

# Block: git reset --hard without specific ref (too broad)
if echo "$first_line" | grep -qE '^\s*git\s+reset\s+--hard\s*$'; then
  echo "BLOCKED: git reset --hard (no ref) — specify a commit or use git stash" >&2
  exit 2
fi

# CSRP P3 — destructive-op guard: blind worktree reverts silently discard another
# live lane's uncommitted hunks (basher s260617-231315 incident). Redirect to
# revert-mine.sh, which snapshots to refs/recovery/ FIRST, then reverts. Catches the
# path-revert forms ONLY — branch switches (git checkout <branch> / -b) are allowed.
if echo "$first_line" | grep -qE '^\s*git\s+checkout\s+(--\s|\.\s*$|\.\s)' \
   || { echo "$first_line" | grep -qE '^\s*git\s+restore\s' && ! echo "$first_line" | grep -qE '\-\-staged'; } \
   || echo "$first_line" | grep -qE '^\s*git\s+clean\s+-[a-zA-Z]*f'; then
  echo "BLOCKED: blind git checkout/restore/clean can discard another live lane's uncommitted work." >&2
  echo "  Use the recoverable path:  WAI-Harness/spoke/managed/tools/revert-mine.sh -- <paths>   (snapshots to refs/recovery/ first)" >&2
  echo "  Or, if you are sure:        revert-mine.sh --reset-hard | --clean | --check <path>" >&2
  exit 2
fi

# CSRP add-side guard (impl-csrp-git-add-commit-interceptor-v1) — symmetric twin of P3.
# `git add -A`/`--all`/`.` or `git commit -a/-am` on a CONTENDED shared tree can sweep
# another live lane's staged files into your commit (the S45 hazard). Route through
# commit-mine.sh, which scopes safely. Reuses commit-mine's own verdict logic
# (isolated worktree OR sole live lane -> allow). Fails OPEN on any resolution error
# so it never bricks commits in non-WAI repos.
if echo "$first_line" | grep -qE '^\s*git\s+add\s+(-A|--all|\.)(\s|$)' \
   || echo "$first_line" | grep -qE '^\s*git\s+commit\s+(-a|-am|--all)'; then
  repo="$(git rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$repo" ]; then
    main="$(git -C "$repo" worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2; exit}')"; main="${main:-$repo}"
    isolated=0; [ "$repo" != "$main" ] && isolated=1
    wg="$main/WAI-Harness/spoke/managed/tools/worktree_guard.py"
    base="$main/WAI-Harness/spoke/local"; [ -d "$base" ] || base="$main/WAI-Spoke"
    live=1
    if [ "$isolated" = 0 ] && [ -f "$wg" ]; then
      live="$(python3 "$wg" lanes --base "$base" 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("count",1))' 2>/dev/null || echo 1)"
    fi
    if [ "$isolated" = 0 ] && [ "${live:-1}" -gt 1 ]; then
      echo "BLOCKED (CSRP): git add -A / commit -a on a CONTENDED shared tree ($live live lanes) can sweep another lane's staged files." >&2
      echo "  Use:  WAI-Harness/spoke/managed/tools/commit-mine.sh -m \"msg\" -- <your paths>   (scopes to your files only)" >&2
      echo "  Or isolate:  python3 $wg wt-new <name>   then work in the worktree." >&2
      exit 2
    fi
  fi
fi

# Block: drop database — only on first line
if echo "$first_line" | grep -qiE '^\s*.*drop\s+(database|table)'; then
  echo "BLOCKED: DROP DATABASE/TABLE — destructive DB operation" >&2
  exit 2
fi

# Block: destructive ops on the v4 protected substrate (harness.db, the append-only
# event journal patterns/*.jsonl, and managed/). Authored by wheelwright-framework,
# placed here by Basher and distributed to every spoke: inert where these paths do
# not exist, protective where they do. Edits to this substrate go through the
# sanctioned tools (atomic_write/event_bus/db_writer), never raw rm/truncate/mv.
if echo "$first_line" | grep -qE '(^|[[:space:]/])harness\.db([[:space:]]|$)|/patterns/[^[:space:]]*\.jsonl([[:space:]]|$)|/managed/'; then
  if echo "$first_line" | grep -qE '^\s*\\?(rm|shred|truncate)\s|^\s*mv\s'; then
    echo "BLOCKED: destructive op on a protected harness path (harness.db / patterns/*.jsonl journal / managed/). Append-only substrate — use the sanctioned tool, not raw rm/truncate/mv." >&2
    exit 2
  fi
fi

# Intercept: rm within ~/projects — redirect to trash bin with reflective path
# Matches: rm, rm -f, rm -rf, \rm, \rm -f on files/dirs under ~/projects/
TRASH_BIN="$HOME/projects/trash_bin"
if echo "$first_line" | grep -qE '^\s*\\?rm\s'; then
  # Extract target paths (skip flags)
  targets=$(echo "$first_line" | sed -E 's/^\s*\\?rm\s+(-[a-zA-Z]+\s+)*//g')
  # Only intercept if targets are under ~/projects/
  if echo "$targets" | grep -qE "(^|/)(~/projects/|\$HOME/projects/|/home/[^/]+/projects/)"; then
    # Build the rewritten command: mkdir -p trash dest, mv instead of rm
    rewrite="# Soft-delete: redirected to trash bin"$'\n'
    for target in $targets; do
      # Expand ~ and $HOME
      expanded=$(echo "$target" | sed "s|^~|$HOME|; s|\\\$HOME|$HOME|")
      # Strip the ~/projects/ prefix to get relative path
      rel_path="${expanded#$HOME/projects/}"
      trash_dest="$TRASH_BIN/$rel_path"
      trash_dir=$(dirname "$trash_dest")
      rewrite+="mkdir -p \"$trash_dir\" && mv \"$expanded\" \"$trash_dest\""$'\n'
    done
    echo "SOFT-DELETE: rm intercepted — files moved to $TRASH_BIN/ instead of deleted. Rewrite:" >&2
    echo "$rewrite" >&2
    exit 2
  fi
fi

# Allow everything else — exit 0 silently (no stdout)
exit 0
