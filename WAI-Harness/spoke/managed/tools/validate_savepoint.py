#!/usr/bin/env python3
"""Resume-contract gate for savepoints (spec-savepoint-resume-contract-v1).

A savepoint is a RESUME CONTRACT, not a summary (P12 Resumable Completeness).
This is the deterministic, mechanical half of the gate (spec-ceremony-lean-v1:
mechanical work extracted to a script; the wai-savepoint skill is the thin
judgment wrapper that composes the fields and calls this before writing).

The contract test: a fresh no-context agent must resume and act, asking the user
nothing knowable at save time. This module asserts the STRUCTURAL preconditions
of that test:

  - first_actions non-empty (the resuming agent has an executable first step)
  - every deferred[].where_captured resolves to a real lug/file (nothing "lost")
  - every pending_handoffs[] carries how_to_verify AND fallback_if_not_done
  - every work_done[] item with verified=false has a matching honest_flag
    ("probably done" banned, P2/P12)
  - paper_trail.topics and paper_trail.decisions non-empty when the session
    touched any lugs (empty arrays no longer acceptable)

It does NOT enforce any length cap (the v3 60-char resume_note cap is removed).

CLI:
    python3 tools/validate_savepoint.py <savepoint.json> [--spoke-root DIR]
    exit 0 = contract satisfied; exit 1 = failures (printed, one per line).
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wai_paths  # noqa: E402  harness-mode root resolver (single source of truth)


def _is_nonempty_list(v):
    return isinstance(v, list) and len(v) > 0


def _lug_dirs(spoke_root):
    """The lug tree(s) to search for a captured lug, harness-mode-aware.
    The active harness's lugs dir is authoritative; in v3/coexist the legacy
    WAI-Spoke/lugs is included as a read-only fallback during the overlap window.
    In v4-only ($WAI_HARNESS_MODE=v4-only) only the v4 tree is consulted — zero
    WAI-Spoke access (spec-savepoint-resume-contract-v1 + V4-COMPLETE Phase B)."""
    dirs = []
    active = wai_paths.category(spoke_root, "lugs")
    if active:
        dirs.append(active)
    # overlap-window fallback: legacy v3 lugs, only when not forced v4-only
    if (os.environ.get("WAI_HARNESS_MODE", "").lower() not in ("v4", "v4-only", "v4only")):
        legacy = os.path.join(spoke_root, "WAI-Spoke", "lugs")
        if legacy not in dirs and os.path.isdir(legacy):
            dirs.append(legacy)
    return dirs


def resolve_capture(where_captured, spoke_root="."):
    """A deferred item is 'not lost' only if where_captured points to something
    that actually exists: an existing file path (relative to spoke_root or
    absolute), or a lug id discoverable under the active harness's lug tree."""
    if not where_captured or not isinstance(where_captured, str):
        return False
    wc = where_captured.strip()
    # 1. direct path (relative-from-root or absolute)
    if os.path.exists(wc) or os.path.exists(os.path.join(spoke_root, wc)):
        return True
    # 2. lug id: search the resolved lug tree(s) for {id}.json
    lug_id = wc[:-5] if wc.endswith(".json") else wc
    for d in _lug_dirs(spoke_root):
        if glob.glob(os.path.join(d, "**", lug_id + ".json"), recursive=True):
            return True
    return False


_DECISION_WORDS = (" pick ", " choose ", " decide ", " which ", " or ", "?")


def validate_resume_contract(sp, spoke_root="."):
    """Validate a savepoint dict against the resume contract.

    Returns {"ok": bool, "failures": [str,...], "warnings": [str,...]}. ok is True
    only when failures is empty (warnings never block). Pure (no writes) so the skill
    can call it before deciding to write.

    Hardened S45 after a resume session hit avoidable friction: a savepoint must say
    WHERE to work (workspace), its first action must be DECIDED (not a fork the resumer
    must stop and ask about), and it should snapshot the inbox + flag auth-gated steps.
    """
    failures = []
    warnings = []

    # --- first_actions: the resuming agent must have an executable first step ---
    fa = sp.get("first_actions")
    if not _is_nonempty_list(fa):
        failures.append(
            "first_actions empty — a resuming agent has no executable first step "
            "(thin savepoint rejected)"
        )
    else:
        for i, a in enumerate(fa):
            if not isinstance(a, dict) or not a.get("action"):
                failures.append(f"first_actions[{i}] missing 'action'")

    # --- work_done: itemized with evidence; unverified items need an honest_flag ---
    wd = sp.get("work_done")
    honest_flags = sp.get("honest_flags") or []
    if not _is_nonempty_list(wd):
        failures.append("work_done empty or not an itemized list (one-line summary banned)")
    else:
        has_unverified = False
        for i, item in enumerate(wd):
            if not isinstance(item, dict):
                failures.append(
                    f"work_done[{i}] is not an object {{what, evidence, verified}} "
                    "(thin string summary banned)"
                )
                continue
            if "verified" not in item:
                failures.append(f"work_done[{i}] missing 'verified' boolean")
            elif item.get("verified") is False:
                has_unverified = True
        if has_unverified and not _is_nonempty_list(honest_flags):
            failures.append(
                "work_done has unverified item(s) (verified=false) but honest_flags "
                "is empty — 'probably done' is banned (P2/P12)"
            )

    # --- pending_handoffs: each must carry how_to_verify AND fallback ---
    for i, h in enumerate(sp.get("pending_handoffs") or []):
        if not isinstance(h, dict):
            failures.append(f"pending_handoffs[{i}] is not an object")
            continue
        if not h.get("how_to_verify"):
            failures.append(f"pending_handoffs[{i}] missing how_to_verify")
        if not h.get("fallback_if_not_done"):
            failures.append(
                f"pending_handoffs[{i}] missing fallback_if_not_done — "
                "re-creates the hand-feeding tax on the next session"
            )

    # --- deferred: every item must be captured somewhere that exists ---
    for i, d in enumerate(sp.get("deferred") or []):
        if not isinstance(d, dict):
            failures.append(f"deferred[{i}] is not an object")
            continue
        wc = d.get("where_captured")
        if not wc:
            failures.append(
                f"deferred[{i}] ('{d.get('item','?')}') missing where_captured — "
                "a deferred item with no capture is a LOST item"
            )
        elif not resolve_capture(wc, spoke_root):
            failures.append(
                f"deferred[{i}] where_captured '{wc}' does not resolve to an "
                "existing lug/file — lost item"
            )

    # --- paper_trail.topics/decisions: non-empty when the session touched lugs ---
    pt = sp.get("paper_trail") or {}
    touched = bool((pt.get("lugs_completed") or []) or (pt.get("lugs_opened") or [])
                   or (pt.get("lugs_in_flight") or []))
    if touched:
        if not _is_nonempty_list(pt.get("topics")):
            failures.append(
                "paper_trail.topics empty for a session that touched lugs "
                "(empty arrays no longer acceptable)"
            )
        if not _is_nonempty_list(pt.get("decisions")):
            failures.append(
                "paper_trail.decisions empty for a session that touched lugs "
                "(empty arrays no longer acceptable)"
            )

    # --- workspace: WHERE to work must be stated (removes framework-vs-mywheel ambiguity) ---
    ws = sp.get("workspace")
    if not (isinstance(ws, dict) and ws.get("path")) and not (isinstance(ws, str) and ws.strip()):
        failures.append(
            "workspace missing — the savepoint must state which tree to work in (e.g. "
            "{path, why}); a resumer should never have to ask 'framework or mywheel?'"
        )

    # --- first_actions[0] must be DECIDED, not a fork the resumer stops on (warning) ---
    if _is_nonempty_list(fa) and isinstance(fa[0], dict):
        a0 = (fa[0].get("action") or "").lower()
        if any(w in f" {a0} " for w in _DECISION_WORDS):
            warnings.append(
                "first_actions[0] reads like a decision/fork (pick/choose/which/or/?). The "
                "resumer must be able to EXECUTE it with no decision — make the call here, "
                "list the alternative as a fallback, not a question."
            )

    # --- inbox snapshot: so the resumer isn't surprised by inbox-first work (warning) ---
    if "inbox_snapshot" not in sp:
        warnings.append(
            "no inbox_snapshot — record what is in lugs/incoming/ at save time so the resumer's "
            "inbox-first pass surfaces nothing unexpected."
        )

    return {"ok": not failures, "failures": failures, "warnings": warnings}


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    spoke_root = "."
    for a in argv:
        if a.startswith("--spoke-root="):
            spoke_root = a.split("=", 1)[1]
    if "--spoke-root" in argv:
        i = argv.index("--spoke-root")
        if i + 1 < len(argv):
            spoke_root = argv[i + 1]
            args = [a for a in args if a != spoke_root]
    if not args:
        print("usage: validate_savepoint.py <savepoint.json> [--spoke-root DIR]", file=sys.stderr)
        return 2
    sp = json.load(open(args[0]))
    result = validate_resume_contract(sp, spoke_root)
    for w in result.get("warnings", []):
        print(f"  ⚠ {w}")
    if result["ok"]:
        print(f"OK — resume contract satisfied: {args[0]}"
              + (f" ({len(result['warnings'])} warning(s))" if result.get("warnings") else ""))
        return 0
    print(f"FAIL — resume contract NOT satisfied ({len(result['failures'])} issue(s)):")
    for f in result["failures"]:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
