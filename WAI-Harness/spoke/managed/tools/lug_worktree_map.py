#!/usr/bin/env python3
"""lug_worktree_map.py — cross-worktree lug reconciliation map.

The fleet runs many concurrent sessions, each in its own git worktree
(.worktrees/<name>) on its own session branch. A lug created or advanced in one
worktree on an unmerged branch is INVISIBLE from any other worktree's filesystem,
so work silently strands on branches nobody merges (S135: 8 worktrees, 7 branches
ahead of main, 3 auto-ejects). Lugs now carry an `origin` block (worktree/branch/
sha, stamped by lug_utils.resolve_worktree_origin at creation + every write); this
tool consumes it.

It walks `git worktree list`, scans each worktree's lug store, and builds a map of
  lug_id -> [ {worktree, branch, status, type, path, origin_*} per copy ]
so reconciliation can answer: where is this work, what state is each copy in, and
which copies are SPREAD (live only in a non-main worktree / disagree on status).

Run modes:
  (default)   human summary: spread + status-divergent lugs first, then totals
  --json      machine-readable {lugs, spread, divergent, worktrees}
  --spread-only   only lugs that exist nowhere on main's branch (stranded work)

Read-only. Never mutates a lug.
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

LUG_GLOB = "WAI-Harness/spoke/local/lugs/bytype/*/*/*.json"
LEGACY_GLOB = "WAI-Spoke/lugs/bytype/*/*/*.json"


def _git(cwd, *args):
    try:
        out = subprocess.run(["git", "-C", cwd, *args],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def list_worktrees(repo="."):
    """Return [{path, branch}] for every git worktree of repo (porcelain-parsed)."""
    raw = _git(repo, "worktree", "list", "--porcelain")
    if not raw:
        # not a multi-worktree setup — treat the repo root as the only tree
        top = _git(repo, "rev-parse", "--show-toplevel") or os.path.abspath(repo)
        br = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
        return [{"path": top, "branch": br}]
    trees, cur = [], {}
    for line in raw.splitlines():
        if line.startswith("worktree "):
            if cur:
                trees.append(cur)
            cur = {"path": line[len("worktree "):], "branch": None}
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch "):].replace("refs/heads/", "")
        elif line.startswith("detached"):
            cur["branch"] = "(detached)"
    if cur:
        trees.append(cur)
    return trees


def scan_worktree(wt_path):
    """Yield (lug_id, record) for every lug json in this worktree's store."""
    base = Path(wt_path)
    for pattern in (LUG_GLOB, LEGACY_GLOB):
        for f in base.glob(pattern):
            try:
                d = json.loads(f.read_text())
            except Exception:
                continue
            lid = d.get("id") or f.stem
            # folder-status is ground truth for placement; json status as backup
            folder_status = f.parent.name
            origin = d.get("origin")
            if not isinstance(origin, dict):  # legacy lugs used origin as a free string
                origin = {}
            yield lid, {
                "worktree": os.path.basename(wt_path.rstrip("/")) or wt_path,
                "worktree_path": wt_path,
                "branch": None,  # filled by caller from worktree branch
                "status": d.get("status") or folder_status,
                "folder_status": folder_status,
                "type": d.get("type"),
                "path": str(f),
                "origin_worktree": origin.get("worktree_name"),
                "origin_branch": origin.get("branch"),
                "origin_sha": origin.get("git_sha"),
            }


def build_map(repo="."):
    worktrees = list_worktrees(repo)
    lugs = defaultdict(list)
    main_branches = {"main", "master"}
    for wt in worktrees:
        wt_path, branch = wt["path"], wt.get("branch")
        for lid, rec in scan_worktree(wt_path):
            rec["branch"] = branch
            lugs[lid].append(rec)
    return worktrees, lugs, main_branches


def classify(lugs, main_branches):
    """spread = lug present in NO main/master worktree (stranded off-main);
    divergent = copies disagree on status."""
    spread, divergent = [], []
    for lid, copies in lugs.items():
        on_main = any((c["branch"] in main_branches) for c in copies)
        if not on_main:
            spread.append(lid)
        statuses = {c["status"] for c in copies}
        if len(statuses) > 1:
            divergent.append(lid)
    return sorted(spread), sorted(divergent)


def main(argv):
    ap = argparse.ArgumentParser(description="Cross-worktree lug reconciliation map.")
    ap.add_argument("--repo", default=".", help="any path inside the git repo")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--spread-only", action="store_true",
                    help="only lugs that live nowhere on main (stranded work)")
    args = ap.parse_args(argv)

    worktrees, lugs, main_branches = build_map(args.repo)
    spread, divergent = classify(lugs, main_branches)

    if args.json:
        print(json.dumps({
            "worktrees": worktrees,
            "lug_count": len(lugs),
            "spread": spread,
            "divergent": divergent,
            "lugs": {lid: copies for lid, copies in lugs.items()
                     if (not args.spread_only or lid in spread)},
        }, indent=2))
        return 0

    print(f"=== lug worktree map — {len(worktrees)} worktree(s), {len(lugs)} distinct lug(s) ===")
    for wt in worktrees:
        print(f"  {os.path.basename(wt['path'].rstrip('/')) or wt['path']:32s} {wt.get('branch')}")
    print()
    show = spread if args.spread_only else sorted(set(spread) | set(divergent))
    if not show:
        print("No stranded or status-divergent lugs — every lug reachable from main. ✅")
        return 0
    print(f"⚠ {len(spread)} stranded off-main, {len(divergent)} status-divergent:\n")
    for lid in show:
        copies = lugs[lid]
        tag = []
        if lid in spread:
            tag.append("STRANDED")
        if lid in divergent:
            tag.append("DIVERGENT")
        print(f"• {lid}  [{', '.join(tag)}]")
        for c in copies:
            print(f"    {c['status']:12s} {c['branch'] or '?':28s} {c['worktree']}")
    print("\nTo handle: cd into the listed worktree/branch (or merge it to main), then "
          "reconcile. `--json` for machine output; `--spread-only` to focus stranded work.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
