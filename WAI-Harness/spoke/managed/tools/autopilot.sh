#!/usr/bin/env bash
# tools/autopilot.sh — Ozi autopilot wrapper
#
# Usage:
#   ./tools/autopilot.sh [budget]
#   ./tools/autopilot.sh [budget] --spoke /path/to/spoke
#   ./tools/autopilot.sh --spoke /path/to/spoke [budget]
#
# budget defaults to 1. Pass any integer.
# --spoke/-s overrides auto-detection (walks up from CWD for WAI-Spoke/).
#
# Examples:
#   ./tools/autopilot.sh          # budget 1, spoke = auto-detect from CWD
#   ./tools/autopilot.sh 3        # budget 3
#   ./tools/autopilot.sh --spoke ~/projects/minder 3

set -euo pipefail

BUDGET=1
SPOKE_PATH=""

# ── Arg parse ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --spoke|-s)
            SPOKE_PATH="$2"
            shift 2
            ;;
        [0-9]*)
            BUDGET="$1"
            shift
            ;;
        -h|--help)
            sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 1
            ;;
    esac
done

# ── Auto-detect spoke (walk up from CWD) ───────────────────────────────────
if [[ -z "$SPOKE_PATH" ]]; then
    dir="$(pwd)"
    while [[ "$dir" != "/" ]]; do
        if [[ -d "$dir/WAI-Spoke" ]]; then
            SPOKE_PATH="$dir"
            break
        fi
        dir="$(dirname "$dir")"
    done
fi

if [[ -z "$SPOKE_PATH" ]]; then
    echo "❌  No WAI-Spoke/ found walking up from $(pwd)" >&2
    echo "    Pass --spoke PATH explicitly." >&2
    exit 1
fi

# ── Locate ozi_autopilot.py relative to this script ────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOPILOT="$SCRIPT_DIR/ozi_autopilot.py"

if [[ ! -f "$AUTOPILOT" ]]; then
    echo "❌  ozi_autopilot.py not found at $AUTOPILOT" >&2
    exit 1
fi

# ── Run ────────────────────────────────────────────────────────────────────
echo "🤖  autopilot | spoke: $SPOKE_PATH | budget: $BUDGET"
echo ""
python3 "$AUTOPILOT" --spoke-path "$SPOKE_PATH" --budget "$BUDGET"
