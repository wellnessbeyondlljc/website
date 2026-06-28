#!/usr/bin/env bash
# revert-mine — the DESTRUCTIVE-side safety net for concurrent sessions.
#
# commit-mine.sh guards the ADD side (`git add -A` sweeping another lane's files).
# This is its symmetric twin for the hole that actually caused data loss
# (basher s260617-231315): a blind `git checkout -- <file>` / `git restore` /
# `git reset --hard` / `git clean -fd` SILENTLY discards another live lane's
# uncommitted hunks. CSRP pillar P3.
#
# Rule: NEVER blind-discard. Snapshot the current dirty state to a recovery ref
# FIRST (recoverable via `git stash apply <ref>` or `git show`), THEN perform the
# revert on only the named paths. If you lose work, it is in refs/recovery/.
#
# Usage:
#   revert-mine -- <path> ...     # snapshot, then `git checkout -- <paths>`
#   revert-mine --reset-hard      # snapshot, then `git reset --hard`
#   revert-mine --clean           # snapshot (incl. untracked), then `git clean -fd`
#   revert-mine --check <path>    # report whether <path> carries uncommitted hunks (no action)
#   revert-mine --list            # list existing recovery refs
set -euo pipefail

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "revert-mine: not in a git repo" >&2; exit 1; }
ts="$(date -u +%Y%m%dT%H%M%SZ)"
lane="$(basename "$REPO")"
recref="refs/recovery/${lane}-${ts}"

snapshot() {
  # git stash create makes a commit object WITHOUT touching the working tree.
  # Capture tracked changes; also note untracked for --clean.
  local obj
  obj="$(git -C "$REPO" stash create "revert-mine snapshot ${ts}" 2>/dev/null || true)"
  if [ -n "$obj" ]; then
    git -C "$REPO" update-ref "$recref" "$obj"
    echo "revert-mine: snapshot saved -> $recref"
    echo "  recover with:  git stash apply $recref      (or: git show $recref)"
  else
    echo "revert-mine: working tree clean (tracked) — nothing to snapshot."
  fi
}

mode="${1:-}"
case "$mode" in
  --check)
    shift; p="${1:?revert-mine --check <path>}"
    if ! git -C "$REPO" diff --quiet -- "$p" || ! git -C "$REPO" diff --cached --quiet -- "$p"; then
      echo "revert-mine: $p HAS uncommitted hunks — revert via 'revert-mine -- $p' (snapshots first), not raw git checkout."
      exit 3
    fi
    echo "revert-mine: $p is clean."
    ;;
  --list)
    git -C "$REPO" for-each-ref --sort=-creatordate --format='%(refname)  %(creatordate:iso)' refs/recovery/ || echo "(none)"
    ;;
  --reset-hard)
    snapshot; echo "revert-mine: git reset --hard"; git -C "$REPO" reset --hard
    ;;
  --clean)
    # snapshot tracked AND stage untracked into the snapshot so clean is recoverable
    git -C "$REPO" add -A -- . >/dev/null 2>&1 || true
    snapshot
    git -C "$REPO" reset -q >/dev/null 2>&1 || true
    echo "revert-mine: git clean -fd"; git -C "$REPO" clean -fd
    ;;
  --)
    shift
    [ "$#" -gt 0 ] || { echo "revert-mine: name the path(s) to revert" >&2; exit 2; }
    snapshot
    echo "revert-mine: git checkout -- $*"
    git -C "$REPO" checkout -- "$@"
    ;;
  *)
    echo "revert-mine: usage: revert-mine [-- <path>... | --reset-hard | --clean | --check <path> | --list]" >&2
    exit 2
    ;;
esac
