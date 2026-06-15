#!/bin/bash
#
# WAI PostToolUse Hook — Python syntax check + lug → Supabase sync.
# Fires after Write and Edit. Always exits 0 — advisory only.
#

input=$(cat)
tool=$(echo "$input" | jq -r '.tool_name // ""')

# ── Emit activity event: tool_call ────────────────────────────────────────
# Fire-and-forget — must not block post-tool-use. Fires for ALL tools.
REPO_ROOT_ACTIVITY="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SESSION_ID_ACTIVITY=$(ls -t "$REPO_ROOT_ACTIVITY/WAI-Spoke/sessions/" 2>/dev/null | head -1 || echo "unknown")
python3 "$REPO_ROOT_ACTIVITY/WAI-Spoke/db/activity.py" tool_call "$tool" "$SESSION_ID_ACTIVITY" 2>/dev/null || true

[[ "$tool" != "Write" && "$tool" != "Edit" ]] && exit 0

file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""')
[[ -z "$file_path" ]] && exit 0
[[ ! -f "$file_path" ]] && exit 0

# Resolve repo root from this script's location.
HOOK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HOOK_DIR/../.." && pwd)"

# --- Python syntax check ------------------------------------------------
if [[ "$file_path" == *.py ]]; then
  RESULT=$(python3 -m py_compile "$file_path" 2>&1)
  if [[ $? -ne 0 ]]; then
    echo "<post-tool-warning>"
    echo "Python syntax error in $file_path:"
    echo "$RESULT"
    echo "</post-tool-warning>"
  fi
fi

# --- Fire-and-forget lug → Supabase upsert ------------------------------
# Match WAI-Spoke/lugs/bytype/<type>/<status>/<id>.json (relative or absolute).
if [[ "$file_path" == *"/WAI-Spoke/lugs/bytype/"*.json ]]; then
  SYNC="$REPO_ROOT/tools/supabase_lug_sync.py"
  if [[ -f "$SYNC" ]]; then
    (python3 "$SYNC" "$file_path" >/dev/null 2>&1 &) >/dev/null 2>&1
  fi
fi

exit 0
