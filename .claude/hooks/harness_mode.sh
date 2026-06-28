#!/bin/bash
# harness_mode.sh — v3/v4 coexistence resolver, sourced by every hook.
#
# The v4 upgrade is non-destructive: a spoke gains a WAI-Harness/ folder beside its
# legacy WAI-Spoke/. Both can be present at once. This resolver lets the SAME .claude
# hooks run v4 while TOLERATING v3 legacy files — so nothing breaks during the overlap
# window, and if something was missed in v4 we can still fall back to v3 to patch.
#
# Usage (in a hook):
#   source "$(dirname "$0")/harness_mode.sh" "$PROJECT_DIR"
#   [ "$HARNESS_ACTIVE" = "v4" ] && ...   # branch on the active harness
#
# Exports (never errors — pure detection, v3-safe):
#   HARNESS_V3      1 if WAI-Spoke/   present else 0
#   HARNESS_V4      1 if WAI-Harness/ present else 0
#   HARNESS_MODE    coexist | v4-only | v3-only | none
#   HARNESS_ACTIVE  v4 | v3 | none   (which one this invocation drives)
#   HARNESS_ROOT    absolute path of the active harness dir ("" if none)
#
# Active selection: an explicit WAI_HARNESS_MODE env override wins (this is how
# "which hub folder you run from" is expressed); otherwise prefer v4 when present
# (built for v4) but fall back to v3 (the legacy path stays usable for patching).

_hm_root="${1:-${PROJECT_DIR:-.}}"

HARNESS_V3=0; HARNESS_V4=0
[ -d "$_hm_root/WAI-Spoke" ]   && HARNESS_V3=1
[ -d "$_hm_root/WAI-Harness" ] && HARNESS_V4=1

if [ "$HARNESS_V3" = 1 ] && [ "$HARNESS_V4" = 1 ]; then HARNESS_MODE="coexist"
elif [ "$HARNESS_V4" = 1 ]; then HARNESS_MODE="v4-only"
elif [ "$HARNESS_V3" = 1 ]; then HARNESS_MODE="v3-only"
else HARNESS_MODE="none"; fi

# active: explicit override first, else OVERLAP-SAFE auto-resolution.
case "${WAI_HARNESS_MODE:-}" in
  v4) [ "$HARNESS_V4" = 1 ] && HARNESS_ACTIVE="v4" || HARNESS_ACTIVE="" ;;
  v3) [ "$HARNESS_V3" = 1 ] && HARNESS_ACTIVE="v3" || HARNESS_ACTIVE="" ;;
  *)  HARNESS_ACTIVE="" ;;
esac
if [ -z "$HARNESS_ACTIVE" ]; then
  if [ "$HARNESS_MODE" = "coexist" ]; then
    # Overlap-safe default: a coexist spoke (both trees present) stays v3 UNTIL it is
    # explicitly ACTIVATED (.activated marker or a migrated v4 local/WAI-State.json).
    # This stops a coexist spoke from silently flipping to v4 mid-overlap, while
    # already-cutover spokes (e.g. basher, which still has a lingering WAI-Spoke/ dir)
    # correctly stay v4 via their activation marker.
    if [ -e "$_hm_root/WAI-Harness/spoke/.activated" ] || [ -f "$_hm_root/WAI-Harness/spoke/local/WAI-State.json" ]; then
      HARNESS_ACTIVE="v4"
    else
      HARNESS_ACTIVE="v3"
    fi
  elif [ "$HARNESS_V4" = 1 ]; then HARNESS_ACTIVE="v4"
  elif [ "$HARNESS_V3" = 1 ]; then HARNESS_ACTIVE="v3"
  else HARNESS_ACTIVE="none"; fi
fi

case "$HARNESS_ACTIVE" in
  v4) HARNESS_ROOT="$_hm_root/WAI-Harness" ;;
  v3) HARNESS_ROOT="$_hm_root/WAI-Spoke" ;;
  *)  HARNESS_ROOT="" ;;
esac

export HARNESS_V3 HARNESS_V4 HARNESS_MODE HARNESS_ACTIVE HARNESS_ROOT
