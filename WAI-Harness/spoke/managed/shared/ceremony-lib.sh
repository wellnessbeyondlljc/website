#!/usr/bin/env bash
# ceremony-lib.sh — shared ceremony preamble (P1 of initiative-optimize-ceremonies-v1).
#
# Single source of truth for the BASE/TOOLS resolution every WAI ceremony
# (wakeup/savepoint/closeout) previously inlined 3-5x. Source it, then call
# `ceremony_init` to export $BASE and $TOOLS (harness-mode-aware: v4-only ->
# WAI-Harness/spoke/local, v3/coexist -> WAI-Spoke). A change to harness-mode
# resolution now happens HERE, once, not in every ceremony.
#
# Usage (top of any ceremony bash block):
#     source WAI-Harness/spoke/managed/shared/ceremony-lib.sh && ceremony_init
#     # -> $BASE and $TOOLS are now set (relative to the spoke root)

_ceremony_tools() {
    local t="WAI-Harness/spoke/managed/tools"
    [ -d "$t" ] || t="tools"
    printf '%s' "$t"
}

# ceremony_base: the active data-plane base, relative to the spoke root.
ceremony_base() {
    local tools b
    tools="$(_ceremony_tools)"
    b=$(python3 "$tools/wai_paths.py" --root . --json 2>/dev/null \
        | python3 -c "import json,sys,os; v=json.load(sys.stdin).get('_base') or ''; print(os.path.relpath(v) if v else '')" 2>/dev/null)
    if [ -z "$b" ]; then
        if [ -d WAI-Harness/spoke/local ]; then b="WAI-Harness/spoke/local"; else b="WAI-Spoke"; fi
    fi
    printf '%s' "$b"
}

# ceremony_init: export BASE + TOOLS for the rest of the ceremony.
ceremony_init() {
    export TOOLS; TOOLS="$(_ceremony_tools)"
    export BASE; BASE="$(ceremony_base)"
}

# csrp_pre_check: read-and-warn concurrent-session notice before a commit (best-effort).
csrp_pre_check() {
    local base="${1:-$BASE}" tools="${TOOLS:-$(_ceremony_tools)}"
    [ -x "$tools/csrp_notice_check.sh" ] && "$tools/csrp_notice_check.sh" --base "$base" 2>/dev/null || true
}
