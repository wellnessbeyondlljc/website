#!/bin/bash
#
# Thin SessionStart wrapper for Wheelwright spokes.
# If the canonical spoke hook exists, delegate to it. Otherwise exit quietly.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# I-1 guard (resolve-check, NOT absolute-path materialization): ${CLAUDE_PROJECT_DIR}
# is the canon hook-path variable — docs-confirmed to expand across all hook events, so
# it stays. Its ONE failure mode is an unset/unresolved value, which would silently break
# every ${CLAUDE_PROJECT_DIR}-based hook command. This is the first hook to run, so make
# that failure LOUD here (degraded-mode JSON) instead of a mute, broken session. An
# environment fault — not a wiring fault; the canonical paths remain correct.
if [ -z "${CLAUDE_PROJECT_DIR:-}" ] || [ ! -d "${CLAUDE_PROJECT_DIR:-/nonexistent}" ]; then
  python3 -c 'import json; print(json.dumps({"hookSpecificOutput": "WAI DEGRADED: CLAUDE_PROJECT_DIR is unset or not a directory — every ${CLAUDE_PROJECT_DIR}-based hook command will fail to resolve. Hook wiring is degraded for this session (environment fault, not a wiring fault). Canonical paths use ${CLAUDE_PROJECT_DIR} per Claude Code docs."}))' 2>/dev/null \
    || echo "WAI DEGRADED: CLAUDE_PROJECT_DIR unset/unresolved — hook paths will not resolve."
fi

# C-2: the canonical spoke session-start hook lives at WAI-Spoke/_hooks/ in most
# spokes (the registered fleet convention — framework/wilbur/track-prompt-lab/why-go-bye)
# and at WAI-Spoke/hooks/ in others (basher dogfood). Probe _hooks/ first, then hooks/.
# The prior bare hooks/ assumption silently lost wakeup in _hooks/-only spokes.
CANONICAL=""
for _cand in "$PROJECT_DIR/WAI-Spoke/_hooks/session-start.sh" "$PROJECT_DIR/WAI-Spoke/hooks/session-start.sh"; do
  [ -x "$_cand" ] && CANONICAL="$_cand" && break
done

# Resolve v3/v4 coexistence (exports HARNESS_ACTIVE / HARNESS_ROOT). v3-safe.
_HM="$(dirname "${BASH_SOURCE[0]:-$0}")/harness_mode.sh"
[ -f "$_HM" ] && source "$_HM" "$PROJECT_DIR" 2>/dev/null

# v4 pull-on-spin-up (own-copy, upgrade-when-newer): bring this spoke's managed/
# current from the master. Cheap no-op when current; never touches local/;
# best-effort + presence-guarded (no-op offline / no master / no WAI-Harness).
# Runs the MASTER's engine so a spoke carrying an old copy still self-updates.
# Master path resolves PORTABLY (clone-and-run on any machine): $WAI_HARNESS_MASTER ->
# per-spoke WAI-Harness/.harness-master -> built-in default. Unreachable -> pull no-ops.
_WMASTER="${WAI_HARNESS_MASTER:-$(cat "$PROJECT_DIR/WAI-Harness/.harness-master" 2>/dev/null)}"
[ -z "$_WMASTER" ] && _WMASTER="/home/mario/projects/wheelwright/mywheel/WAI-Harness"
_HUP="$_WMASTER/spoke/managed/tools/harness_upgrade.py"
[ -f "$_HUP" ] && [ -d "$PROJECT_DIR/WAI-Harness" ] && \
  python3 "$_HUP" pull --spoke-root "$PROJECT_DIR" --master "$_WMASTER" >/dev/null 2>&1

# v4 on-load trigger: notice the upgrade and, ONLY when WAI-Harness/ACTIVATE
# exists, migrate. Dormant + idempotent + dry-run-first by design — safe to call
# every load. Presence-guarded: no-op where the harness isn't installed.
# stdout->/dev/null: SessionStart hook stdout must stay clean for the canonical.
_HACT="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/harness_activate.py"
[ -f "$_HACT" ] && python3 "$_HACT" --spoke-root "$PROJECT_DIR" check >/dev/null 2>&1

# v4 concurrency: if another live session exists for this spoke, isolate this one in
# a git worktree (worktree_guard handles detection — single-session is zero-cost).
# worktree_guard.py ships under managed/tools (v4 canon); fall back to root tools/
# (v3 dogfood). M-7 fix: the prior bare $PROJECT_DIR/tools/ check was dead wiring
# fleet-wide because the tool only ships under managed/. Presence-guarded.
_WG=""
for _c in "$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py" "$PROJECT_DIR/tools/worktree_guard.py"; do
  [ -f "$_c" ] && _WG="$_c" && break
done
[ -n "$_WG" ] && python3 "$_WG" 2>/dev/null

# v4 liveness indicator: emit ONE visible line so a human can SEE v4 is live in the
# session banner. This is the only stdout this wrapper produces; v3-only spokes
# (no WAI-Harness/) stay silent. Printed before exec so it lands above the canonical
# wakeup output. ASCII separators only (no em-dash) to stay encoding-safe.
[ "$HARNESS_V4" = "1" ] && echo "[v4 ACTIVE] managed current | mode=$HARNESS_MODE active=$HARNESS_ACTIVE"

if [[ -n "$CANONICAL" && -x "$CANONICAL" ]]; then
  exec "$CANONICAL"
fi

# v4-only: no v3 canonical hook, but a v4 harness IS present -> run the mode-aware
# canonical wakeup that ships in managed (renders the briefing from WAI-Harness/spoke/local).
# This is what makes a v4-only spoke (no WAI-Spoke tree) wake up with a full briefing.
_V4WAKE="$(dirname "${BASH_SOURCE[0]:-$0}")/wakeup-canonical.sh"
if [ -d "$PROJECT_DIR/WAI-Harness/spoke/local" ] && [ -x "$_V4WAKE" ]; then
  exec "$_V4WAKE"
fi

# C-2: no canonical hook found. If this spoke HAS a WAI-Spoke tree, wakeup is broken —
# say so LOUDLY (degraded JSON) instead of a silent exit 0 that mutely skips the briefing.
if [ -d "$PROJECT_DIR/WAI-Spoke" ]; then
  python3 -c 'import json; print(json.dumps({"hookSpecificOutput": "WAI DEGRADED: no canonical session-start hook found at WAI-Spoke/_hooks/ or WAI-Spoke/hooks/ — the wakeup briefing did NOT run this session."}))' 2>/dev/null \
    || echo "WAI DEGRADED: no canonical session-start hook (WAI-Spoke/_hooks|hooks) — wakeup did not run."
fi
exit 0
