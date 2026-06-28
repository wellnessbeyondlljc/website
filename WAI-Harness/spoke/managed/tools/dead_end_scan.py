#!/usr/bin/env python3
"""dead_end_scan.py — the no-loose-ends gate (initiative-no-dead-ends-v1 +
initiative-optimize-ceremonies-v1 P3).

A "dead-end" is work with no durable home and no tracked disposition. This scans a
repo for the classes that bit us in practice and reports them so a ceremony can
BLOCK (savepoint/closeout) or SURFACE (wakeup) rather than let work silently strand.

Classes detected (per repo / worktree):
  - uncommitted        tracked files modified/deleted but not committed
  - untracked_source   untracked, non-gitignored SOURCE files (*.py/.sh/.md/.js/.ts/
                       .json/.yaml/.sql/...) that exist in no ref — the orphan-source
                       dead-end (lives only in a working tree / stash)
  - unpushed           commits on the current branch ahead of its upstream (or, if no
                       upstream, ahead of origin/main) — reunified-but-unpublished
  - stashes            git stashes (off-history; a stash without a tracking lug is a
                       dead-end by definition)
  - branches_ahead     local session/* branches with commits not in main (stranded
                       branch work — the reunification class; informational at session
                       scope, actionable at fleet scope)

`clean` is True when the SESSION-scope classes (uncommitted, untracked_source,
unpushed, stashes) are all empty. branches_ahead is reported but does not by itself
fail the session gate (it is a fleet/reunification concern).

CLI:
  python3 dead_end_scan.py [--root .] [--json] [--scope session|fleet]
Exit: 0 clean | 1 dead-ends found | 2 error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

SOURCE_EXT = (
    ".py", ".sh", ".bash", ".js", ".ts", ".jsx", ".tsx", ".md", ".json", ".jsonl",
    ".yaml", ".yml", ".sql", ".toml", ".rb", ".go", ".rs", ".css", ".html",
)


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _is_repo(root):
    return _git(root, "rev-parse", "--is-inside-work-tree").returncode == 0


def scan(root=".", scope="session") -> dict:
    if not _is_repo(root):
        return {"ok": False, "error": f"not a git repo: {root}"}

    uncommitted, untracked_source = [], []
    st = _git(root, "status", "--porcelain").stdout.splitlines()
    for line in st:
        if not line.strip():
            continue
        code, path = line[:2], line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[-1].strip()
        if code == "??":
            if any(path.endswith(e) for e in SOURCE_EXT):
                untracked_source.append(path)
        else:
            uncommitted.append(path)

    # unpushed: ahead of upstream, else ahead of origin/main
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
    ref = upstream if upstream and "fatal" not in upstream else "origin/main"
    cnt = _git(root, "rev-list", "--count", f"{ref}..HEAD").stdout.strip()
    unpushed = int(cnt) if cnt.isdigit() else 0

    stashes = [s for s in _git(root, "stash", "list").stdout.splitlines() if s.strip()]

    branches_ahead = []
    if scope == "fleet" or True:  # cheap; always compute (session scope just won't gate on it)
        for b in _git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads/").stdout.splitlines():
            b = b.strip()
            if not b or b == "main":
                continue
            ahead = _git(root, "rev-list", "--count", f"main..{b}").stdout.strip()
            if ahead.isdigit() and int(ahead) > 0:
                branches_ahead.append({"branch": b, "ahead": int(ahead)})

    session_dead_ends = bool(uncommitted or untracked_source or unpushed or stashes)
    clean = not session_dead_ends
    return {
        "ok": True, "clean": clean, "scope": scope, "branch": branch,
        "uncommitted": uncommitted,
        "untracked_source": untracked_source,
        "unpushed": unpushed,
        "stashes": stashes,
        "branches_ahead": branches_ahead,
        "summary": (f"{len(uncommitted)} uncommitted, {len(untracked_source)} untracked-source, "
                    f"{unpushed} unpushed, {len(stashes)} stash(es), "
                    f"{len(branches_ahead)} branch(es) ahead of main"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Scan for dead-end work (no-loose-ends gate).")
    ap.add_argument("--root", default=".")
    ap.add_argument("--scope", choices=["session", "fleet"], default="session")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rep = scan(args.root, scope=args.scope)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0 if rep.get("clean") else (2 if "error" in rep else 1)
    if "error" in rep:
        print(f"dead_end_scan: ERROR — {rep['error']}", file=sys.stderr)
        return 2
    if rep["clean"]:
        print(f"no dead-ends: CLEAN — {rep['summary']}")
        if rep["branches_ahead"]:
            print(f"  (note: {len(rep['branches_ahead'])} branch(es) ahead of main — fleet reunification, not a session blocker)")
        return 0
    print(f"DEAD-ENDS FOUND — {rep['summary']}")
    for p in rep["uncommitted"]:
        print(f"  [uncommitted]      {p}")
    for p in rep["untracked_source"]:
        print(f"  [untracked-source] {p}  (orphan — commit, lug, or discard-with-reason)")
    if rep["unpushed"]:
        print(f"  [unpushed]         {rep['unpushed']} commit(s) ahead of {rep['branch']} upstream")
    for s in rep["stashes"]:
        print(f"  [stash]            {s}  (pair with a tracking lug or drop)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
