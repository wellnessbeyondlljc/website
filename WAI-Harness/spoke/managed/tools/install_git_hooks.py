#!/usr/bin/env python3
"""install_git_hooks.py — install the WAI pre-commit secret hook into a spoke (Fable MR-2).

The Fable review found ZERO pre-commit hooks across the fleet. This installer wires the
managed `.githooks/pre-commit` (secret scanner) into a spoke via `core.hooksPath`, which is
update-friendly (the hook stays a single tracked file, no per-spoke copy drifts) and safe
because the fleet has no pre-existing hooks to displace.

What it does (idempotent):
  1. seeds `<root>/.githooks/pre-commit` and `<root>/.gitleaks.toml` from the managed template
     if absent (so existing spokes can retrofit without a full template re-sync),
  2. makes the hook executable,
  3. sets `git config core.hooksPath .githooks` (warns first if custom hooks already exist).

Usage:
  python3 tools/install_git_hooks.py [--spoke-path .] [--force]
Exit: 0 installed / already-current | 1 error.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

_MANAGED_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "spoke"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def _repo_root(spoke_path: str) -> Path | None:
    r = _git(Path(spoke_path), "rev-parse", "--show-toplevel")
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def _seed(dst: Path, src: Path, executable: bool = False) -> str:
    if dst.exists():
        return "present"
    if not src.exists():
        return f"template-missing:{src}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if executable:
        dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return "seeded"


def install(spoke_path: str = ".", force: bool = False) -> dict:
    root = _repo_root(spoke_path)
    if root is None:
        return {"ok": False, "error": f"{spoke_path} is not inside a git repo"}

    report = {"ok": True, "root": str(root), "actions": []}

    hook = root / ".githooks" / "pre-commit"
    report["actions"].append(
        f"hook: {_seed(hook, _MANAGED_TEMPLATE / '.githooks' / 'pre-commit', executable=True)}")
    if hook.exists():  # ensure executable even if it was already present
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    report["actions"].append(
        f"gitleaks-config: {_seed(root / '.gitleaks.toml', _MANAGED_TEMPLATE / '.gitleaks.toml')}")

    if not hook.exists():
        return {"ok": False, "error": "no pre-commit hook to install (template missing)", **report}

    # Warn (don't clobber) if the spoke already has custom hooks under the default path.
    default_hooks = root / ".git" / "hooks"
    existing = [p.name for p in default_hooks.glob("*")
                if p.is_file() and not p.name.endswith(".sample")] if default_hooks.is_dir() else []
    cur = _git(root, "config", "--get", "core.hooksPath").stdout.strip()
    if existing and cur != ".githooks" and not force:
        report["ok"] = False
        report["error"] = (f"existing custom hooks in .git/hooks ({existing}) — re-run with --force "
                           f"to switch core.hooksPath to .githooks (those hooks would be bypassed)")
        return report

    if cur == ".githooks":
        report["actions"].append("core.hooksPath: already .githooks")
    else:
        r = _git(root, "config", "core.hooksPath", ".githooks")
        if r.returncode != 0:
            return {"ok": False, "error": f"git config failed: {r.stderr.strip()}", **report}
        report["actions"].append("core.hooksPath: set to .githooks")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Install the WAI pre-commit secret hook (Fable MR-2).")
    ap.add_argument("--spoke-path", default=".")
    ap.add_argument("--force", action="store_true",
                    help="switch core.hooksPath even if custom .git/hooks exist")
    args = ap.parse_args(argv)

    rep = install(args.spoke_path, args.force)
    for a in rep.get("actions", []):
        print(f"  {a}")
    if rep["ok"]:
        print(f"✓ WAI pre-commit hook active in {rep['root']} (bypass a commit with --no-verify)")
        return 0
    print(f"✖ {rep.get('error')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
