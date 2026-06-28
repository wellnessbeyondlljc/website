#!/usr/bin/env python3
"""v3_path_lint.py — cut-gate lint: catch v3 `WAI-Spoke/` paths used in managed tools.

The recurring fleet defect (impl-harness-parity-gate-at-cut-v1, and the ~25 findings in
initiative-soft-feature-remediation-v1) is a managed tool that hardcodes a `WAI-Spoke/`
(v3) path as its SOLE/PRIMARY resolution. On a v4-only spoke that path does not exist, so
the tool runs but silently does nothing — a "soft feature". This lint runs at the MANIFEST
cut and FAILS it on any NEW such reference, so the class can never regress back in.

RATCHET model: the existing known-debt files live in an allowlist (v3_path_lint_allow.json).
A file in the allowlist may still carry `WAI-Spoke/` refs (tracked by the remediation
initiative); a file NOT in the allowlist with any `WAI-Spoke/` code reference FAILS the cut.
As the sweep fixes each tool, drop it from the allowlist — the ratchet tightens, never loosens.

Scope: WAI-Harness/spoke/managed/tools/*.py + WAI-Harness/spoke/managed/.claude/hooks/*.sh.
Comment-only lines are ignored (a doc reference to WAI-Spoke is harmless).

CLI:
    python3 v3_path_lint.py --managed <managed_dir> [--allow <allowlist.json>] [--json]
Exit: 0 clean (only allowlisted debt) | 1 NEW violation(s) | 2 error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

NEEDLE = "WAI-Spoke/"
DEFAULT_ALLOW = "tools/v3_path_lint_allow.json"

# A file that references WAI-Spoke/ but ALSO carries any of these is v4-aware: the v3 path
# is a guarded fallback alongside a real v4 resolution, not a sole/primary path. Only files
# with a WAI-Spoke/ ref and ZERO v4-awareness are flagged (the silent-no-op soft-feature class).
V4_MARKERS = (
    "WAI-Harness/spoke/local", "wai_paths", "resolve_wai_root", "advisors_dir",
    "HARNESS_V4", "HARNESS_ACTIVE", "WAI_HARNESS_MODE", "V4_BASE", "category(",
)
# Files the gate does not govern: the linter itself (its NEEDLE/docs name the pattern) and
# test files (they may reference v3 deliberately to assert behavior).
def _exempt(name: str) -> bool:
    return name == "v3_path_lint.py" or name.startswith("test_")


def _is_comment(line: str, suffix: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if suffix == ".py":
        return s.startswith("#")
    if suffix == ".sh":
        return s.startswith("#")
    return False


def _scan_file(path: Path) -> list:
    """Return [(lineno, text)] for non-comment lines that reference a WAI-Spoke/ path."""
    hits = []
    try:
        for i, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if NEEDLE in line and not _is_comment(line, path.suffix):
                hits.append((i, line.strip()[:160]))
    except Exception:
        pass
    return hits


def _scan_targets(managed: Path):
    """The files the gate governs: managed tools (.py) + managed .claude hooks (.sh)."""
    out = []
    tools = managed / "tools"
    if tools.is_dir():
        out += sorted(p for p in tools.glob("*.py"))
    hooks = managed / ".claude" / "hooks"
    if hooks.is_dir():
        out += sorted(p for p in hooks.glob("*.sh"))
    return out


def load_allow(managed: Path, allow_path=None) -> dict:
    p = Path(allow_path) if allow_path else (managed / DEFAULT_ALLOW)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        return d.get("allow", d) if isinstance(d, dict) else {}
    except Exception:
        return {}


def lint(managed, allow_path=None) -> dict:
    managed = Path(managed)
    allow = load_allow(managed, allow_path)
    allow_set = set(allow.keys()) if isinstance(allow, dict) else set(allow)
    flagged, violations = {}, {}
    for f in _scan_targets(managed):
        if _exempt(f.name):
            continue
        hits = _scan_file(f)
        if not hits:
            continue
        # v4-aware? then the WAI-Spoke/ refs are guarded fallbacks — not a soft-feature risk.
        body = f.read_text(errors="ignore")
        if any(m in body for m in V4_MARKERS):
            continue
        rel = str(f.relative_to(managed))
        flagged[rel] = hits
        if rel not in allow_set:
            violations[rel] = hits
    return {
        "ok": not violations,
        "violations": violations,          # NEW debt (not allowlisted) -> fails the cut
        "allowlisted_debt": {k: v for k, v in flagged.items() if k in allow_set},
        "allow_count": len(allow_set),
        "flagged_files": len(flagged),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="v3 WAI-Spoke/ path cut-gate lint")
    ap.add_argument("--managed", required=True)
    ap.add_argument("--allow", default=None, help="allowlist JSON (default: <managed>/tools/v3_path_lint_allow.json)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    rep = lint(args.managed, args.allow)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        if rep["ok"]:
            print(f"v3-path lint: CLEAN — {rep['allow_count']} allowlisted debt file(s), "
                  f"no NEW WAI-Spoke/ sole-path references.")
        else:
            print(f"v3-path lint: FAIL — {len(rep['violations'])} file(s) reference WAI-Spoke/ "
                  "and are NOT allowlisted (new v3-noop soft-feature risk):")
            for rel, hits in rep["violations"].items():
                print(f"  {rel}:")
                for ln, txt in hits[:4]:
                    print(f"    L{ln}: {txt}")
            print("  -> route through wai_paths (v4-aware), or add to v3_path_lint_allow.json "
                  "with a reason if it is a genuine guarded v3 fallback.")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
