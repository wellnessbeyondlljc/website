#!/usr/bin/env python3
"""Teaching delivery folder structure initializer — idempotent setup.

Creates the two-tier teaching delivery folder structure under
hub/WAI-Spoke/hub/teachings/ per spec-teaching-delivery-system-v1.

CLI:
  python3 tools/teaching_delivery_init.py [--hub-path <path>]
  Default hub path: /home/mario/projects/wheelwright/hub
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_HUB_PATH = "/home/mario/projects/wheelwright/hub"
INITIAL_MANIFEST_VERSION = "1.0.0"

SUBDIRS = ["staging", "hot-patches", "consolidated", "archive"]


def init_teaching_structure(hub_path: str | Path) -> dict:
    hub = Path(hub_path)
    teachings_root = hub / "WAI-Spoke" / "hub" / "teachings"

    if not teachings_root.exists():
        return {"ok": False, "error": f"teachings root not found: {teachings_root}"}

    created = []
    already_existed = []

    for subdir in SUBDIRS:
        d = teachings_root / subdir
        if d.exists():
            already_existed.append(str(d))
        else:
            d.mkdir(parents=True, exist_ok=True)
            (d / ".gitkeep").touch()
            created.append(str(d))

    manifest_path = teachings_root / "base-version-manifest.json"
    manifest_created = False
    if not manifest_path.exists():
        manifest = {
            "current_version": INITIAL_MANIFEST_VERSION,
            "cuts": []
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        manifest_created = True
        created.append(str(manifest_path))
    else:
        already_existed.append(str(manifest_path))

    return {
        "ok": True,
        "hub_path": str(hub),
        "teachings_root": str(teachings_root),
        "created": created,
        "already_existed": already_existed,
        "manifest_created": manifest_created,
    }


def _main(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Initialize hub teaching delivery folder structure")
    p.add_argument("--hub-path", default=DEFAULT_HUB_PATH)
    args = p.parse_args(argv)

    result = init_teaching_structure(args.hub_path)
    if not result["ok"]:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        return 1

    if result["created"]:
        for path in result["created"]:
            print(f"  CREATED  {path}")
    if result["already_existed"]:
        for path in result["already_existed"]:
            print(f"  EXISTS   {path}")

    print(f"OK: teaching delivery structure ready at {result['teachings_root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
