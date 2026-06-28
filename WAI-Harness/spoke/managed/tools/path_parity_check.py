#!/usr/bin/env python3
"""path_parity_check.py — managed-copy v3->v4 path-parity gate (P12 followup #4).

The recurring failure class across this harness has been a managed RESOLVER (an
executed tool/hook or a live model-instruction command/skill) that reads or WRITES a
data path under the legacy v3 root `WAI-Spoke/<runtime|sessions|savepoints>/` with NO
v4 counterpart. On a cutover (v4) spoke that does one of two harmful things:

  - WRITE: recreates a `WAI-Spoke/` phantom husk (the P12 savepoint-circuit breaker —
    auto-eject / ozi-sessions / track-flush leaking to v3); or
  - READ:  silently no-ops because the real data now lives under WAI-Harness/spoke/local
    (the dormant-advisor bug class — Phase-2.5 scouts, expediter v3 paths).

Same bug shape recurred in: ozi_autopilot Phase-2.5 scouts, the expediter, the UPS hook,
stop-savepoint-guard, and the wai-auto-* ozi-sessions writers. A per-cut parity gate is
the durable guard the spec called for.

DESIGN — regression gate, not an absolute gate. The managed tree still carries many
historical unpaired refs (some legitimate, some latent). Remediating all at once is a
separate effort; what matters at the cut is that NO NEW one slips in. So we snapshot the
known set as a baseline and FAIL only on additions. `--baseline` re-snapshots after an
intentional change; `--check` (default) compares and exits non-zero on any NEW finding.

A finding is suppressed when its file ALSO references the v4 base (`WAI-Harness/spoke/local`)
or a coexistence resolver (`HARNESS_ACTIVE`, `wai_paths`) — i.e. the path is already
mode-aware. Surface is restricted to RESOLVERS (tools/hooks/commands/skills/enter-exit),
never specs/teachings/tests/reference docs, which mention v3 paths descriptively.

API (pure over an injected managed dir, unit-testable):
  scan(managed_dir) -> {rel_path: [husk_subdir,...]}
  diff(current, baseline) -> {"new": {...}, "fixed": {...}}

CLI:
  path_parity_check.py <managed_dir> [--baseline] [--check] [--baseline-path P] [--json]
"""
import argparse
import json
import os
import re
import sys

# husk-recreating / no-op data subdirs under the v3 root
HUSK_RE = re.compile(r"WAI-Spoke/(runtime|sessions|savepoints)/")
V4_BASE = "WAI-Harness/spoke/local"
COEXIST_TOKENS = ("HARNESS_ACTIVE", "wai_paths")  # file is already mode-aware
DEFAULT_BASELINE = "config/path_parity_baseline.json"  # relative to managed_dir

_EXCLUDE_DIRS = {"__pycache__", ".git", ".pytest_cache"}
# descriptive surfaces that legitimately mention v3 paths (not data-plane resolvers)
_DESCRIPTIVE = ("knowledge/spec/", "shared/teachings/", "tests/", "wilbur/docs/",
                "/reference/", "templates/harness-base/")
_DESCRIPTIVE_SUFFIX = (".teaching", ".spec.md", ".spec", ".pyc", ".pyo")


def _in_surface(rel):
    """True if rel is a data-plane RESOLVER (executed code or live model-instruction)."""
    r = rel.replace(os.sep, "/")
    if r == "MANIFEST.json":
        return False
    if r.endswith(_DESCRIPTIVE_SUFFIX):
        return False
    if any(seg in r for seg in _DESCRIPTIVE):
        return False
    return (r.endswith((".py", ".sh")) or "/commands/" in r or "/skills/" in r
            or "/.claude/hooks/" in r or "/hooks/" in r)


def scan(managed_dir):
    """Map each unpaired v3-husk-path resolver -> sorted list of husk subdirs it touches."""
    out = {}
    for dirpath, dirs, files in os.walk(managed_dir):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS]
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, managed_dir).replace(os.sep, "/")
            if not _in_surface(rel):
                continue
            try:
                s = open(full, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            kinds = sorted(set(HUSK_RE.findall(s)))
            if not kinds:
                continue
            if V4_BASE in s or any(tok in s for tok in COEXIST_TOKENS):
                continue  # already mode-aware -> not unpaired
            out[rel] = kinds
    return out


def diff(current, baseline):
    """New = unpaired ref present now but not baselined (a regression to block).
    Fixed = baselined ref no longer present (cleanup credit; prune from baseline)."""
    new = {k: v for k, v in current.items() if k not in baseline}
    fixed = {k: v for k, v in baseline.items() if k not in current}
    return {"new": new, "fixed": fixed}


def _load_baseline(path):
    if os.path.exists(path):
        try:
            return json.load(open(path)).get("unpaired", {})
        except (ValueError, OSError):
            return {}
    return {}


def main(argv=None):
    ap = argparse.ArgumentParser(description="managed v3->v4 path-parity regression gate")
    ap.add_argument("managed_dir")
    ap.add_argument("--baseline", action="store_true",
                    help="re-snapshot the current unpaired set as the accepted baseline")
    ap.add_argument("--check", action="store_true",
                    help="compare to baseline; exit 1 on any NEW unpaired ref (default action)")
    ap.add_argument("--baseline-path", default=None,
                    help=f"baseline file (default {DEFAULT_BASELINE} under managed_dir)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    bpath = a.baseline_path or os.path.join(a.managed_dir, DEFAULT_BASELINE)
    current = scan(a.managed_dir)

    if a.baseline:
        os.makedirs(os.path.dirname(bpath), exist_ok=True)
        json.dump({"_doc": "P12 path-parity gate baseline — known unpaired v3-husk-path "
                           "resolvers. Gate fails only on NEW additions. Re-run "
                           "path_parity_check.py --baseline after an intentional change.",
                   "count": len(current), "unpaired": current},
                  open(bpath, "w"), indent=2, sort_keys=True)
        print(f"[path_parity] baselined {len(current)} unpaired resolver(s) -> {bpath}")
        return 0

    baseline = _load_baseline(bpath)
    d = diff(current, baseline)
    if a.json:
        print(json.dumps({"current": len(current), "baseline": len(baseline), **d}, indent=2))
    else:
        print(f"[path_parity] current={len(current)} baseline={len(baseline)} "
              f"NEW={len(d['new'])} fixed={len(d['fixed'])}")
        for rel, kinds in sorted(d["new"].items()):
            print(f"  NEW v3-husk-path (BLOCKS CUT): {rel} -> WAI-Spoke/{{{','.join(kinds)}}}/")
        for rel in sorted(d["fixed"]):
            print(f"  fixed (prune from baseline): {rel}")
    return 1 if d["new"] else 0


if __name__ == "__main__":
    sys.exit(main())
