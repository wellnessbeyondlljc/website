#!/usr/bin/env bash
# csrp_mode — the CSRP-aware savepoint/closeout auto-detect predicate.
# Spec: spec-csrp-aware-savepoint-closeout-mode-v1 (operator directive 2026-06-18:
# CSRP-aware mode applies AUTOMATICALLY, Ozi-level, NEVER prompts the human).
#
# Returns whether savepoint/closeout must enter CSRP-aware (git-safe-under-concurrency)
# mode, and the reason. Callers (wai-savepoint/closeout, P6 converge_closeout.py,
# ozi_autopilot.py) gate their git posture on this. Prints JSON: {csrp_aware, reason}.
# Always exits 0 (a query); fail-OPEN to normal mode on any resolution error.
#
# Triggers (ANY -> csrp_aware):
#   (a) contended:        non-isolated tree with >1 live lane (safe_to_commit:false)
#   (b) canonical-elsewhere: this repo is NOT the master (MANIFEST.is_master != true) -> dogfood
#   (c) incoming notice:  a CSRP/reconcile/remote-mod notice is pending in incoming/
#   (d) [gated on AC4 lane-capture] unauthored tracked changes — not yet detectable
# Usage: csrp_mode.sh [--base <store-root>]
set -euo pipefail

BASE=""
while [ $# -gt 0 ]; do case "$1" in --base) BASE="${2:-}"; shift 2 ;; *) shift ;; esac; done

repo="$(git rev-parse --show-toplevel 2>/dev/null || true)"
csrp=false; reasons=()

if [ -n "$repo" ]; then
  main="$(git -C "$repo" worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2; exit}')"; main="${main:-$repo}"
  isolated=0; [ "$repo" != "$main" ] && isolated=1
  wg="$main/WAI-Harness/spoke/managed/tools/worktree_guard.py"
  [ -n "$BASE" ] || { BASE="$main/WAI-Harness/spoke/local"; [ -d "$BASE" ] || BASE="$main/WAI-Spoke"; }

  # (a) contended shared tree
  live=1
  if [ "$isolated" = 0 ] && [ -f "$wg" ]; then
    live="$(python3 "$wg" lanes --base "$BASE" 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("count",1))' 2>/dev/null || echo 1)"
  fi
  if [ "$isolated" = 0 ] && [ "${live:-1}" -gt 1 ]; then csrp=true; reasons+=("contended:${live}-lanes"); fi

  # (b) canonical home is elsewhere (this repo is a dogfood, not the master)
  manifest="$main/WAI-Harness/spoke/managed/MANIFEST.json"
  if [ -f "$manifest" ]; then
    ismaster="$(python3 -c 'import json,sys;print(str(json.load(open(sys.argv[1])).get("is_master")).lower())' "$manifest" 2>/dev/null || echo true)"
    [ "$ismaster" != "true" ] && { csrp=true; reasons+=("canonical-elsewhere"); }
  fi

  # (c) pending CSRP/reconcile/remote-mod notice in incoming/ (csrp_notice_check exits 10 when present)
  nc="$main/WAI-Harness/spoke/managed/tools/csrp_notice_check.sh"
  if [ -f "$nc" ]; then
    bash "$nc" --base "$BASE" --all --no-mark >/dev/null 2>&1 && ncrc=0 || ncrc=$?
    [ "${ncrc:-0}" = 10 ] && { csrp=true; reasons+=("incoming-csrp-notice"); }
  fi
fi

reason="$(IFS=,; echo "${reasons[*]:-none}")"
printf '{"csrp_aware": %s, "reason": "%s"}\n' "$csrp" "$reason"
[ "$csrp" = true ] && echo "  CSRP-aware close (trigger: $reason) — scope adds via commit-mine, push branch (no merge to a dogfood main), state to gitignored local, surface notices first." >&2 || true
exit 0
