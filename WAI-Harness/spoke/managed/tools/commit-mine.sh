#!/usr/bin/env bash
# commit-mine — the shared-tree safety net for concurrent sessions.
#
# The only real hazard when two sessions share ONE working tree is `git add -A`
# sweeping the OTHER session's in-flight files into your commit (the S45 silent
# revert). This helper makes a safe commit by reusing worktree_guard's ownership
# verdict instead of trusting the human to remember to scope:
#
#   - in an isolated worktree, OR sole live session  -> you own the tree;
#       `git add -A` is safe; commit everything.
#   - shared tree + other live sessions              -> NEVER add -A; stage only
#       the paths you pass and commit just those (exit 3 if you passed none).
#
# Normally you never need this: wai-enter auto-isolates the 2nd+ session into its own
# worktree, where `git add -A` is always safe. commit-mine is the fallback for a
# deliberately shared tree (WAI_NO_ISOLATE=1, or a session that pre-dates isolation).
#
# Per-lane edited-file capture (so this could auto-derive "my files") is a Phase-2
# follow-up gated on the track-enrichment fix; until then the contended case requires
# you to name your files — but the rule is ENFORCED, not merely advised.
#
# Usage:  commit-mine -m "message" [-- <path> ...]
#         commit-mine -m "message" path/a path/b
set -euo pipefail

MSG=""; PATHS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -m) MSG="${2:-}"; shift 2 ;;
    --) shift; PATHS=("$@"); break ;;
    *)  PATHS+=("$1"); shift ;;
  esac
done
[ -n "$MSG" ] || { echo "commit-mine: -m <message> required" >&2; exit 2; }

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "commit-mine: not in a git repo" >&2; exit 1; }
MAIN="$(git -C "$REPO" worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2; exit}')"
MAIN="${MAIN:-$REPO}"
WG="$MAIN/WAI-Harness/spoke/managed/tools/worktree_guard.py"
BASE="$MAIN/WAI-Harness/spoke/local"; [ -d "$BASE" ] || BASE="$MAIN/WAI-Spoke"

# isolated if our checkout root differs from the main worktree root
ISOLATED=0; [ "$REPO" != "$MAIN" ] && ISOLATED=1
LIVE=1
if [ -f "$WG" ]; then
  LIVE="$(python3 "$WG" lanes --base "$BASE" 2>/dev/null \
          | python3 -c 'import sys,json;print(json.load(sys.stdin).get("count",1))' 2>/dev/null || echo 1)"
fi

if [ "$ISOLATED" = 1 ] || [ "${LIVE:-1}" -le 1 ]; then
  echo "commit-mine: you own this tree (isolated=$ISOLATED live=$LIVE) — git add -A is safe."
  git add -A
else
  if [ "${#PATHS[@]}" -eq 0 ]; then
    echo "commit-mine: SHARED tree with $LIVE live sessions and you are NOT isolated." >&2
    echo "  Refusing 'git add -A' — it would sweep another session's files." >&2
    echo "  Re-run naming only YOUR files:  commit-mine -m \"$MSG\" -- path/a path/b" >&2
    echo "  (or isolate next time via wai-enter, which auto-worktrees the 2nd session)" >&2
    exit 3
  fi
  echo "commit-mine: shared tree, $LIVE live — staging ONLY your ${#PATHS[@]} path(s)."
  git add -- "${PATHS[@]}"
fi

echo "--- staged set ---"; git diff --cached --name-only
git commit -m "$MSG"
