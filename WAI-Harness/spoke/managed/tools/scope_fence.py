#!/usr/bin/env python3
"""scope_fence.py — keep agent writes inside the active lug's declared file_targets.

Part of the execution sandbox (impl-execution-sandbox-foundation-v1). Given a
lug id and an attempted write path, assert the path is one of that lug's
file_targets. If it is not, the write is flagged (and the caller stages rather
than applies to live) — a hallucinating agent cannot silently mutate files
outside the work it was dispatched for.

API:
  file_targets(lug_id, lugs_root=...) -> [paths] | None
  check_scope(lug_id, write_path, lugs_root=...)
      -> {"in_scope": bool, "flagged": bool, "file_targets": [...], "lug_found": bool}
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _default_lugs_root(spoke_root="."):
    """The lugs/bytype root, base-aware. On a v4 spoke this resolves under
    WAI-Harness/spoke/local; PRE-FIX the hardcoded WAI-Spoke path made every
    scope check fail-closed (lug never found) on v4 (impl-fix-p2-v3noop-sweep-v1)."""
    try:
        from wai_paths import resolve_wai_root
        root, mode = resolve_wai_root(str(spoke_root))
        if root and mode != "none":
            return os.path.join(root, "lugs", "bytype")
    except Exception:
        pass
    return os.path.join("WAI-Spoke", "lugs", "bytype")  # last-resort v3 fallback


DEFAULT_LUGS_ROOT = _default_lugs_root()


def _find_lug(lug_id, lugs_root):
    for path in glob.glob(os.path.join(lugs_root, "*", "*", f"{lug_id}.json")):
        return path
    return None


def file_targets(lug_id, lugs_root=DEFAULT_LUGS_ROOT):
    p = _find_lug(lug_id, lugs_root)
    if not p:
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return list(d.get("file_targets", []))


def _norm(path):
    return os.path.normpath(path).lstrip("./")


def check_scope(lug_id, write_path, lugs_root=DEFAULT_LUGS_ROOT):
    """Return whether write_path is inside lug_id's file_targets. If the lug is
    not found, fail closed (flagged=True) — an unknown scope is not a license."""
    targets = file_targets(lug_id, lugs_root)
    if targets is None:
        return {"in_scope": False, "flagged": True, "file_targets": [], "lug_found": False}
    wn = _norm(write_path)
    in_scope = any(_norm(t) == wn for t in targets)
    return {"in_scope": in_scope, "flagged": not in_scope,
            "file_targets": targets, "lug_found": True}


def main(argv=None):
    ap = argparse.ArgumentParser(description="check a write path against a lug's file_targets")
    ap.add_argument("lug_id")
    ap.add_argument("write_path")
    ap.add_argument("--lugs-root", default=DEFAULT_LUGS_ROOT)
    a = ap.parse_args(argv)
    res = check_scope(a.lug_id, a.write_path, a.lugs_root)
    print(json.dumps(res))
    return 0 if res["in_scope"] else 1


if __name__ == "__main__":
    sys.exit(main())
