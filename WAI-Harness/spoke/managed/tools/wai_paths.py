#!/usr/bin/env python3
"""wai_paths.py — the single source of truth for WHERE a spoke's working state lives.

This is the Python counterpart to `.claude/hooks/harness_mode.sh`. Every ceremony
(session-start/wakeup, closeout, savepoint, track) and every state tool that needs
to read or write spoke working-state MUST resolve its root through here, so that a
`WAI_HARNESS_MODE=v4-only` session runs entirely on the v4 tree with ZERO reads or
writes to the legacy `WAI-Spoke/` tree (V4-COMPLETE-PLAN Phase B, done-criterion 1).

Two harness layouts coexist during the v3->v4 overlap:
  v3 working base = <root>/WAI-Spoke
  v4 working base = <root>/WAI-Harness/spoke/local

Mode selection (overlap-SAFE — v4 is an explicit opt-in, never a silent flip):
  - an explicit mode (arg or $WAI_HARNESS_MODE) wins; tokens v4 / v4-only / v3 /
    v3-only / coexist are all accepted (the bash switch uses v4|v3; the plan and
    docs say v4-only|v3-only — we accept both so neither caller is wrong),
  - else, when BOTH trees are present (coexist), default to v3 — the legacy tree is
    what every live reader still consumes (WAI-Spoke/wakeup-brief.json, the v3
    session-start hook, user-prompt-submit). Auto-flipping a coexist spoke to v4
    would split writes (v4) from reads (v3) across the fleet mid-port. A spoke goes
    v4 only when the operator sets WAI_HARNESS_MODE=v4-only (Phase E cutover) or
    when WAI-Spoke is gone (the end state).
  - else, when ONLY WAI-Harness is present, v4 (the post-retirement end state),
  - else, when ONLY WAI-Spoke is present, v3,
  - else "none".

NOTE — intentional divergence from the current .claude/hooks/harness_mode.sh, whose
auto branch still "prefers v4 when present". That bash resolver is sourced only by the
NOT-YET-REGISTERED v4 hook, so there is no live inconsistency today; harness_mode.sh
must be aligned to this overlap-safe default before any coexist spoke is flipped (a
Basher-owned .claude change — tracked as a change-lug). The explicit-env path already
agrees in both resolvers.

In v4-only the v3 tree is a READ-ONLY fallback and is NEVER required. The category
map matches harness_activate.py HOME_MAP, including the one sibling case: `advisors`
lives at `WAI-Harness/spoke/advisors` (NOT under `local/`) in v4.

Importable API:
    working_base, mode = resolve_wai_root(spoke_root, mode=None)
    paths = wai_paths(spoke_root, mode=None)        # dict: category -> abs path
    p     = category(spoke_root, "savepoints")      # one category, abs path
    info  = detect(spoke_root)                      # has_v3/has_v4/harness_mode/active

CLI (so bash hooks can resolve without re-implementing the logic):
    python3 tools/wai_paths.py --root DIR [--mode v4-only] --category savepoints
        -> prints the absolute path (or empty line if active == none)
    python3 tools/wai_paths.py --root DIR [--mode v4-only] --json
        -> prints the full {category: path, ...} map plus _mode/_base
"""
import argparse
import json
import os
import sys

# Working-state categories that live UNDER the working base (WAI-Spoke in v3,
# WAI-Harness/spoke/local in v4). Mirrors harness_activate.HOME_MAP minus the
# advisors sibling case handled separately below.
LOCAL_CATEGORIES = (
    "WAI-State.json",
    "sessions",
    "lugs",
    "savepoints",
    "initiatives",
    "signals",
    "bolts",
    "teachings",
    "kpi",
    "runtime",
    "wakeup-brief.json",
)


def _normalize_mode(mode):
    """Map any accepted mode token to the canonical v4 / v3 / '' (auto)."""
    m = (mode or os.environ.get("WAI_HARNESS_MODE") or "").strip().lower()
    if m in ("v4", "v4-only", "v4only"):
        return "v4"
    if m in ("v3", "v3-only", "v3only"):
        return "v3"
    # coexist / none / '' all fall through to auto-detection
    return ""


def _v4_activated(root):
    """True if a coexist spoke has been explicitly cut over to v4. Mirrors the
    activation signal used by .claude/hooks/harness_mode.sh (lines 42-52): a
    `.activated` marker OR a migrated v4 local/WAI-State.json. Keeping this in
    lockstep with the bash resolver is REQUIRED — otherwise the hooks run v4 while
    the Python tools read/write v3, splitting state across the two trees."""
    return (
        os.path.exists(os.path.join(root, "WAI-Harness", "spoke", ".activated"))
        or os.path.isfile(os.path.join(root, "WAI-Harness", "spoke", "local", "WAI-State.json"))
    )


def _select_active(want, has_v3, has_v4, v4_activated=False):
    """Resolve the active harness from a normalized mode want ('v4'|'v3'|'') and
    tree presence. Overlap-safe: an UNACTIVATED coexist spoke defaults to v3; an
    ACTIVATED one resolves v4 (matching harness_mode.sh)."""
    if want == "v4" and has_v4:
        return "v4"
    if want == "v3" and has_v3:
        return "v3"
    if has_v3 and has_v4:   # coexist: v4 only once explicitly activated, else v3
        return "v4" if v4_activated else "v3"
    if has_v3:              # v3-only
        return "v3"
    if has_v4:              # only WAI-Harness present -> v4 (post-retirement end state)
        return "v4"
    return "none"


def detect(spoke_root="."):
    """Pure detection (never raises): which trees exist + the resolved active mode."""
    root = os.path.abspath(spoke_root)
    has_v3 = os.path.isdir(os.path.join(root, "WAI-Spoke"))
    has_v4 = os.path.isdir(os.path.join(root, "WAI-Harness"))
    if has_v3 and has_v4:
        harness_mode = "coexist"
    elif has_v4:
        harness_mode = "v4-only"
    elif has_v3:
        harness_mode = "v3-only"
    else:
        harness_mode = "none"

    # detect() takes no explicit mode; honour only the $WAI_HARNESS_MODE override.
    want = _normalize_mode(None)
    active = _select_active(want, has_v3, has_v4, _v4_activated(root))
    return {
        "root": root,
        "has_v3": has_v3,
        "has_v4": has_v4,
        "harness_mode": harness_mode,
        "active": active,
    }


def resolve_wai_root(spoke_root=".", mode=None):
    """Return (working_base, active_mode).

    working_base is the directory under which the working-state categories live for
    the active harness. active_mode is "v4" | "v3" | "none". An explicit `mode` arg
    wins over $WAI_HARNESS_MODE wins over auto (prefer v4, else v3)."""
    root = os.path.abspath(spoke_root)
    has_v3 = os.path.isdir(os.path.join(root, "WAI-Spoke"))
    has_v4 = os.path.isdir(os.path.join(root, "WAI-Harness"))
    want = _normalize_mode(mode)
    active = _select_active(want, has_v3, has_v4, _v4_activated(root))
    if active == "v4":
        return os.path.join(root, "WAI-Harness", "spoke", "local"), "v4"
    if active == "v3":
        return os.path.join(root, "WAI-Spoke"), "v3"
    return None, "none"


def advisors_dir(spoke_root=".", mode=None):
    """Advisors are the one category not under the working base.
    v3: <root>/WAI-Spoke/advisors ; v4: <root>/WAI-Harness/spoke/advisors."""
    root = os.path.abspath(spoke_root)
    _, active = resolve_wai_root(spoke_root, mode)
    if active == "v4":
        return os.path.join(root, "WAI-Harness", "spoke", "advisors")
    if active == "v3":
        return os.path.join(root, "WAI-Spoke", "advisors")
    return None


def wai_paths(spoke_root=".", mode=None):
    """Full {category: absolute_path} map for the active harness, plus _base/_mode.
    Returns {"_mode": "none", "_base": None} if neither tree is present."""
    base, active = resolve_wai_root(spoke_root, mode)
    if base is None:
        return {"_mode": "none", "_base": None}
    out = {"_mode": active, "_base": base}
    for name in LOCAL_CATEGORIES:
        out[name] = os.path.join(base, name)
    out["advisors"] = advisors_dir(spoke_root, mode)
    return out


def category(spoke_root, name, mode=None):
    """Absolute path for a single category in the active harness, or None if no tree.
    `advisors` is resolved to its sibling location; all others sit under the base."""
    if name == "advisors":
        return advisors_dir(spoke_root, mode)
    base, active = resolve_wai_root(spoke_root, mode)
    if base is None:
        return None
    return os.path.join(base, name)


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Resolve WAI working-state paths by harness mode.")
    ap.add_argument("--root", default=".", help="spoke root (contains WAI-Spoke and/or WAI-Harness)")
    ap.add_argument("--mode", default=None, help="v4-only | v3-only | v4 | v3 (else $WAI_HARNESS_MODE / auto)")
    ap.add_argument("--category", default=None, help="print one category's absolute path")
    ap.add_argument("--json", action="store_true", help="print the full category map as JSON")
    ap.add_argument("--detect", action="store_true", help="print detection info as JSON")
    args = ap.parse_args(argv)

    if args.detect:
        print(json.dumps(detect(args.root)))
        return 0
    if args.category:
        p = category(args.root, args.category, args.mode)
        print(p if p else "")
        return 0
    if args.json:
        print(json.dumps(wai_paths(args.root, args.mode)))
        return 0
    base, mode = resolve_wai_root(args.root, args.mode)
    print(base if base else "")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
