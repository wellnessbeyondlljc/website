#!/usr/bin/env python3
"""deploy_commands.py — sync the canonical ceremony/command set to the spoke's
ACTIVE slash-command dir.

The operator's slash commands resolve from <spoke_root>/.claude/commands/. The
CANONICAL source is <spoke_root>/WAI-Harness/spoke/managed/.claude/commands/
(MANIFEST-verified, distributed via harness_upgrade pull). Nothing kept the two in
sync, so the active commands drifted to stale copies (P0 of
initiative-optimize-ceremonies-v1: the operator ran a Jun-5 wai-closeout stub /
a v3 wai-savepoint while the canonical was far ahead).

This tool COPIES every managed command into the active dir (overwriting stale),
PRESERVES active-only local commands (not present in managed), and PRUNES retired
commands (named in RETIRED). Idempotent. Run on pull-on-spin-up + at activate so
the active set can never lag the canonical.

CLI:
    python3 deploy_commands.py --root DIR [--dry-run] [--json]
Exit: 0 ok | 2 error.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import sys
from pathlib import Path

MANAGED_REL = "WAI-Harness/spoke/managed/.claude/commands"
ACTIVE_REL = ".claude/commands"

# Commands retired from the canonical set — remove from the active dir if present.
RETIRED = (
    "wai-closeout-feedback-v2.md",
    "wai-closeout-feedback-v2-slim.md",
)


def _sources(managed_dir: Path):
    return sorted(p for p in managed_dir.glob("*.md") if p.is_file())


def deploy(spoke_root: str, dry_run: bool = True) -> dict:
    root = Path(spoke_root).resolve()
    managed = root / MANAGED_REL
    active = root / ACTIVE_REL
    if not managed.is_dir():
        return {"ok": False, "error": f"managed commands dir not found: {managed}"}
    active.mkdir(parents=True, exist_ok=True)

    copied, current, pruned = [], [], []
    managed_names = set()
    for src in _sources(managed):
        managed_names.add(src.name)
        dst = active / src.name
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            current.append(src.name)
            continue
        copied.append(src.name)
        if not dry_run:
            shutil.copy2(src, dst)

    for name in RETIRED:
        dst = active / name
        if dst.exists():
            pruned.append(name)
            if not dry_run:
                dst.unlink()

    # active-only local commands (preserved, never touched)
    active_only = sorted(
        p.name for p in active.glob("*.md")
        if p.name not in managed_names and p.name not in RETIRED
    )
    return {
        "ok": True, "dry_run": dry_run,
        "managed_dir": str(managed), "active_dir": str(active),
        "copied": copied, "already_current": current, "pruned": pruned,
        "preserved_local": active_only,
        "summary": f"{len(copied)} synced, {len(current)} current, "
                   f"{len(pruned)} pruned, {len(active_only)} local preserved",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deploy canonical commands to the active .claude/commands dir.")
    ap.add_argument("--root", default=".", help="spoke root")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rep = deploy(args.root, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        if not rep.get("ok"):
            print(f"deploy_commands: ERROR — {rep.get('error')}", file=sys.stderr)
            return 2
        tag = "[dry-run] would sync" if args.dry_run else "synced"
        print(f"deploy_commands: {tag} — {rep['summary']}")
        for n in rep["copied"]:
            print(f"  ~ {n}")
        for n in rep["pruned"]:
            print(f"  - {n} (retired)")
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
