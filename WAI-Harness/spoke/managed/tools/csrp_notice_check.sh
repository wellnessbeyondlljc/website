#!/usr/bin/env bash
# csrp_notice_check — CSRP read-and-warn pre-step (impl-ozi-csrp-incoming-check-savepoint-closeout-v1).
#
# Surfaces concurrent-session/reconcile notices that land in {BASE}/lugs/incoming/
# so a session never savepoints/closes/commits IN IGNORANCE of: main being advanced
# by another lane, its own work being unmerged/unpushed, or a remote-mod of its master.
# Call it at the TOP of savepoint/closeout (interactive) and before Ozi's autonomous close.
#
# Scans for: notice-session-reconcile-*.json, notice-remote-mod-*.json, impl-csrp-*.json
# Idempotent: records surfaced ids in {BASE}/runtime/csrp-notices-seen.txt (gitignored);
#   re-runs do not re-surface already-seen notices unless --all is passed.
#
# Usage: csrp_notice_check.sh [--base <store-root>] [--all] [--mark-seen]
# Exit:  0 = no unseen notices (or none);  10 = unseen CSRP notice(s) surfaced (CALLER SHOULD ACKNOWLEDGE/DEFER)
set -euo pipefail

BASE=""; ALL=0; MARK=1
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE="${2:-}"; shift 2 ;;
    --all) ALL=1; shift ;;
    --no-mark) MARK=0; shift ;;
    --mark-seen) MARK=1; shift ;;
    *) shift ;;
  esac
done
# Resolve base: explicit, else v4 local, else v3 fallback
if [ -z "$BASE" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || echo .)"
  BASE="$REPO/WAI-Harness/spoke/local"; [ -d "$BASE" ] || BASE="$REPO/WAI-Spoke"
fi
INC="$BASE/lugs/incoming"
SEEN="$BASE/runtime/csrp-notices-seen.txt"
[ -d "$INC" ] || { exit 0; }

ALL="$ALL" MARK="$MARK" SEEN="$SEEN" python3 - "$INC" <<'PY'
import json, os, sys, glob
inc = sys.argv[1]
all_mode = os.environ.get("ALL") == "1"
mark = os.environ.get("MARK") == "1"
seen_path = os.environ.get("SEEN")
seen = set()
if os.path.exists(seen_path):
    seen = {l.strip() for l in open(seen_path) if l.strip()}

pats = ["notice-session-reconcile-*.json", "notice-remote-mod-*.json", "impl-csrp-*.json"]
files = sorted({f for p in pats for f in glob.glob(os.path.join(inc, p))})
surfaced, flagged = [], False
for f in files:
    try:
        d = json.load(open(f))
    except Exception:
        continue
    lid = d.get("id", os.path.basename(f))
    if not all_mode and lid in seen:
        continue
    surfaced.append(lid)
    what = d.get("what_was_done") or d.get("summary") or d.get("title") or ""
    guide = d.get("per_session_guidance") or d.get("what_spoke_should_own") or ""
    commit = d.get("git_commit", "")
    blob = (json.dumps(d)).lower()
    if any(k in blob for k in ("unmerged", "unpushed", "reconcile up", "diverge")):
        flagged = True
    print(f"  [CSRP] {lid}")
    if commit: print(f"         commit: {commit}")
    if what:   print(f"         what:   {str(what)[:240]}")
    if guide:  print(f"         you:    {str(guide)[:240]}")

if surfaced:
    print(f"\n  {len(surfaced)} CSRP notice(s) surfaced. ACKNOWLEDGE before commit/record; "
          f"DEFER blind-close if any flags this lane's work unmerged/unpushed.")
    if mark:
        os.makedirs(os.path.dirname(seen_path), exist_ok=True)
        with open(seen_path, "a") as fh:
            for lid in surfaced:
                if lid not in seen: fh.write(lid + "\n")
    sys.exit(10)
else:
    print("  [CSRP] no unseen reconcile/remote-mod notices in incoming/.")
    sys.exit(0)
PY
