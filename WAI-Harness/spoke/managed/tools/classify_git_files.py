#!/usr/bin/env python3
"""Classify uncommitted git files into teaching / runtime / unknown buckets.

Faithful extraction of the deterministic block in
.claude/commands/wai-closeout.md, section
"10h. Git Audit — Uncommitted File Classification".

Closeout uses the buckets to decide commit strategy:
  - teaching: auto-commit as a dedicated teaching commit
  - runtime:  auto-skip (ephemeral)
  - unknown:  surface per-file decision

CLI:
  python3 classify_git_files.py --base BASE [--root .]

Prints JSON: {"teaching": [...], "runtime": [...], "unknown": [...]}
"""
import argparse
import json
import subprocess
import sys


def classify(base, root="."):
    """Return {'teaching':[...], 'runtime':[...], 'unknown':[...]} for the
    uncommitted files in the git repo at `root`, using `base` to expand the
    {BASE}-rooted path prefixes (same rules as the inline closeout block)."""
    result = subprocess.run(
        ['git', 'status', '--short'],
        capture_output=True, text=True, cwd=root,
    )
    lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]

    TEACHING_PATHS = (
        '{BASE}/seed/ingest/processed/'.replace('{BASE}', base),
        '.claude/hooks/',
        'CLAUDE.md',
        'AGENTS.md',
    )
    RUNTIME_PATHS = (
        '{BASE}/runtime/'.replace('{BASE}', base),
        '{BASE}/advisors/'.replace('{BASE}', base),
        'wakeup-brief.json',
        '{BASE}/wakeup-brief.json'.replace('{BASE}', base),
        '{BASE}/sessions/'.replace('{BASE}', base),
    )

    teaching_files = []
    runtime_files = []
    unknown_files = []

    for line in lines:
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        path = parts[1].strip()
        if ' -> ' in path:
            path = path.split(' -> ')[-1].strip()
        if any(path.startswith(p) or path == p for p in TEACHING_PATHS):
            teaching_files.append(path)
        elif any(path.startswith(p) or path == p for p in RUNTIME_PATHS):
            runtime_files.append(path)
        else:
            unknown_files.append(path)

    return {
        'teaching': teaching_files,
        'runtime': runtime_files,
        'unknown': unknown_files,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', required=True,
                    help='Spoke BASE path used to expand {BASE} path prefixes')
    ap.add_argument('--root', default='.',
                    help='Git repo root to run git status in (default: .)')
    args = ap.parse_args(argv)
    print(json.dumps(classify(args.base, args.root)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
