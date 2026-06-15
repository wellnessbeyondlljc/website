#!/bin/bash
#
# Thin SessionStart wrapper for Wheelwright spokes.
# If the canonical spoke hook exists, delegate to it. Otherwise exit quietly.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
CANONICAL="$PROJECT_DIR/WAI-Spoke/hooks/session-start.sh"

if [[ -x "$CANONICAL" ]]; then
  exec "$CANONICAL"
fi

exit 0
