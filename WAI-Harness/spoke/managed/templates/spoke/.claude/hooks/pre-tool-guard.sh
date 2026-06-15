#!/bin/bash
#
# PreToolUse Guard — blocks destructive commands at hook level
# Returns JSON with decision: allow/deny/ask
# Stderr output blocks the action; stdout is informational
#

input=$(cat)
tool=$(echo "$input" | jq -r '.tool_name // ""')

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

# Block: drop database — only on first line
if echo "$first_line" | grep -qiE '^\s*.*drop\s+(database|table)'; then
  echo "BLOCKED: DROP DATABASE/TABLE — destructive DB operation" >&2
  exit 2
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
