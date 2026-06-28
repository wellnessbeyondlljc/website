#!/bin/bash
#
# Thin SessionStart wrapper for Wheelwright spokes.
# If the canonical spoke hook exists, delegate to it. Otherwise exit quietly.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# --- Herald responder LIGHT-PATH (WAI_HERALD_SPAWN) ---------------------------
# When Herald spawns a responder (claude -p) for ONE lug, load LIGHT: skip upgrade,
# lane registration, the full wakeup briefing, and never claim chains. The responder
# gets its full instructions from its -p prompt; it only needs to process the one lug.
# This early-exit is also what keeps the Herald auto-spawn below from recursing.
if [ -n "${WAI_HERALD_SPAWN:-}" ]; then
  python3 -c 'import json; print(json.dumps({"hookSpecificOutput":"HERALD RESPONDER - LIGHT MODE. Do NOT run wakeup, do NOT claim chains, do NOT scan the backlog. Process ONLY the lug named in your prompt: read it, follow PEV (perceive/execute/verify), run its verify/tests, commit CSRP-scoped (never git add -A), push your OWN session/herald branch (never main), deliver a completion (or refinement) lug back to the originating spoke, then exit."}))' 2>/dev/null \
    || echo "HERALD RESPONDER (light): process only the assigned lug; no wakeup; no chain-claim; scoped commit; push own branch; confirm back."
  exit 0
fi


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

# v4 concurrency: lane registration (the liveness signal for concurrent-session
# isolation) is done by the canonical wakeup (wakeup-canonical.sh runs
# `worktree_guard.py lane-register --session <cc_sid> --base <base>`), which has the
# SessionStart stdin payload carrying the CC session_id. A bare, argless call here was
# a dead argparse no-op — and a hook could not isolate anyway: a running session cannot
# relocate its own CWD, so SOURCE isolation must happen at LAUNCH (wai-enter auto-
# worktrees the 2nd+ live session), never from inside a hook.
# (impl-basher-concurrent-session-autoisolation-v1: removed the no-op; registration is wakeup-side.)

# v4 liveness indicator: emit ONE visible line so a human can SEE v4 is live in the
# session banner. This is the only stdout this wrapper produces; v3-only spokes
# (no WAI-Harness/) stay silent. Printed before exec so it lands above the canonical
# wakeup output. ASCII separators only (no em-dash) to stay encoding-safe.
[ "$HARNESS_V4" = "1" ] && echo "[v4 ACTIVE] managed current | mode=$HARNESS_MODE active=$HARNESS_ACTIVE"

# Herald auto-spawn (opt-in, session-bound). `start` is idempotent and no-ops unless
# herald.json enabled:true, so calling it on every session start is safe fleet-wide --
# only deliberately-enabled spokes spin a daemon. The daemon self-reaps when the live-
# lane count hits zero, so no stop hook is needed. Backgrounded + silenced so it never
# delays the session. A Herald-spawned responder already exited on the LIGHT path above,
# so this never recurses.
_HERALD="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/herald_poll.py"
[ -f "$_HERALD" ] && ( python3 "$_HERALD" --spoke-root "$PROJECT_DIR" start >/dev/null 2>&1 & ) >/dev/null 2>&1

# v4-native wakeup: the single canonical path. wakeup-canonical.sh is mode-aware —
# it renders the briefing from WAI-Harness/spoke/local (handles coexist + v4-only),
# so any spoke carrying a v4 local tree wakes here regardless of HARNESS_ACTIVE.
_V4WAKE="$(dirname "${BASH_SOURCE[0]:-$0}")/wakeup-canonical.sh"
if [ -d "$PROJECT_DIR/WAI-Harness/spoke/local" ] && [ -x "$_V4WAKE" ]; then
  exec "$_V4WAKE"
fi

# No v4 local tree present. A bare repo (no WAI-Harness/) is simply not a WAI spoke —
# stay silent. But if WAI-Harness/ IS present yet wakeup can't run, say so LOUDLY
# (degraded JSON) instead of a mute exit that silently skips the briefing.
if [ -d "$PROJECT_DIR/WAI-Harness" ]; then
  python3 -c 'import json; print(json.dumps({"hookSpecificOutput": "WAI DEGRADED: WAI-Harness present but no v4 local tree / executable wakeup-canonical.sh — the wakeup briefing did NOT run. Run harness install + activate to adopt v4."}))' 2>/dev/null \
    || echo "WAI DEGRADED: no v4 wakeup (spoke/local + wakeup-canonical.sh) — wakeup did not run."
fi
exit 0
