#!/usr/bin/env python3
"""Teaching delivery cut tool — nightly base consolidation and spoke delivery.

Per spec-teaching-delivery-system-v1:
  check : report staged teaching count vs cap
  cut   : consolidate staged teachings -> versioned upgrade teaching -> deliver to spokes
  auto  : cut if staged_count >= 1 (nightly automation entry point)

Hot-patch delivery:
  hot-patch --teaching <path> --hub-path <path> : validate P0/P1 teaching, deliver to all spokes

CLI:
  python3 tools/teaching_delivery_cut.py check [--hub-path <path>]
  python3 tools/teaching_delivery_cut.py cut   [--hub-path <path>]
  python3 tools/teaching_delivery_cut.py auto  [--hub-path <path>]
  python3 tools/teaching_delivery_cut.py hot-patch --teaching <path> [--hub-path <path>]
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_HUB_PATH = "/home/mario/projects/wheelwright/hub"
HUB_REGISTRY_PATH = "/home/mario/projects/wheelwright/hub/hub-registry.json"
HARD_CAP = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _teachings_root(hub_path: Path) -> Path:
    return hub_path / "WAI-Spoke" / "hub" / "teachings"


def _load_manifest(hub_path: Path) -> dict[str, Any]:
    manifest_path = _teachings_root(hub_path) / "base-version-manifest.json"
    if not manifest_path.exists():
        return {"current_version": "1.0.0", "cuts": []}
    return json.loads(manifest_path.read_text())


def _bump_minor(version: str) -> str:
    parts = version.split(".")
    if len(parts) < 3:
        parts += ["0"] * (3 - len(parts))
    try:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{major}.{minor + 1}.0"
    except (ValueError, IndexError):
        return "1.1.0"


def _load_staged(hub_path: Path) -> list[dict[str, Any]]:
    staging = _teachings_root(hub_path) / "staging"
    teachings = []
    for f in sorted(staging.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            data["_source_file"] = f.name
            teachings.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return teachings


def _active_spokes(registry_path: str | None = None) -> list[dict[str, Any]]:
    path = registry_path or HUB_REGISTRY_PATH
    try:
        reg = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return []
    return [w for w in reg.get("wheels", []) if w.get("status") == "active"]


def check(hub_path: Path) -> dict[str, Any]:
    staged = _load_staged(hub_path)
    count = len(staged)
    return {
        "staged_count": count,
        "cap": HARD_CAP,
        "cut_needed": count >= 1,
        "hard_cap_exceeded": count >= HARD_CAP,
        "staged_ids": [t.get("id", t.get("_source_file", "?")) for t in staged],
    }


def cut(hub_path: Path) -> dict[str, Any]:
    root = _teachings_root(hub_path)
    staged_teachings = _load_staged(hub_path)

    if not staged_teachings:
        return {"action": "noop", "reason": "no staged teachings"}

    manifest = _load_manifest(hub_path)
    current_version = manifest.get("current_version", "1.0.0")
    next_version = _bump_minor(current_version)

    # Build consolidated upgrade teaching
    consolidates = []
    teachings_entries = []
    for t in staged_teachings:
        tid = t.get("id", t.get("_source_file", "unknown"))
        consolidates.append(tid)
        teachings_entries.append({
            "id": tid,
            "title": t.get("title", tid),
            "apply_steps": t.get("apply_steps", []),
            "verification_steps": t.get("verification_steps", []),
        })

    consolidated_id = f"teaching-upgrade-base-v{next_version.replace('.', '-')}"
    consolidated = {
        "id": consolidated_id,
        "type": "consolidated",
        "base_version": next_version,
        "priority": "P2",
        "adopt_asap": False,
        "created_at": _now(),
        "consolidates": consolidates,
        "teachings": teachings_entries,
    }

    # Write consolidated teaching
    consolidated_path = root / "consolidated" / f"{consolidated_id}.json"
    consolidated_path.write_text(json.dumps(consolidated, indent=2) + "\n")

    # Archive staged files to archive/base-vN/
    archive_dir = root / "archive" / f"base-v{next_version}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived_files = []
    for t in staged_teachings:
        src = root / "staging" / t["_source_file"]
        if src.exists():
            dst = archive_dir / t["_source_file"]
            shutil.move(str(src), str(dst))
            archived_files.append(t["_source_file"])

    # Update manifest
    manifest["current_version"] = next_version
    manifest.setdefault("cuts", []).append({
        "version": next_version,
        "cut_at": _now(),
        "teachings_consolidated": consolidates,
        "consolidated_teaching_id": consolidated_id,
        "archive_path": str(archive_dir.relative_to(hub_path)),
    })
    (root / "base-version-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # Deliver to active spokes
    delivered_to = []
    skipped_spokes = []
    for spoke in _active_spokes():
        spoke_path = Path(spoke.get("path", ""))
        incoming = spoke_path / "WAI-Spoke" / "lugs" / "incoming"
        if not incoming.exists():
            skipped_spokes.append(spoke.get("wheel_id", str(spoke_path)))
            continue
        dest = incoming / f"{consolidated_id}.json"
        dest.write_text(json.dumps(consolidated, indent=2) + "\n")
        delivered_to.append(spoke.get("wheel_id", str(spoke_path)))

    return {
        "action": "cut",
        "new_version": next_version,
        "consolidated_teaching_id": consolidated_id,
        "teachings_consolidated": len(consolidates),
        "archived_files": archived_files,
        "delivered_to": delivered_to,
        "skipped_spokes": skipped_spokes,
    }


def auto(hub_path: Path) -> dict[str, Any]:
    status = check(hub_path)
    if not status["cut_needed"]:
        return {"action": "noop", "staged_count": status["staged_count"], "reason": "nothing staged"}
    return cut(hub_path)


def deliver_hot_patch(teaching_path: Path, hub_path: Path) -> dict[str, Any]:
    from validate_teaching import validate_teaching_file

    errors = validate_teaching_file(teaching_path)
    if errors:
        return {"ok": False, "errors": errors}

    data = json.loads(teaching_path.read_text())
    priority = data.get("priority", "")
    if priority not in {"P0", "P1"}:
        return {"ok": False, "errors": [f"hot-patch requires P0/P1 priority, got {priority!r}"]}

    root = _teachings_root(hub_path)
    hot_dest = root / "hot-patches" / teaching_path.name
    shutil.copy2(str(teaching_path), str(hot_dest))

    delivered_to = []
    skipped_spokes = []
    for spoke in _active_spokes():
        spoke_path = Path(spoke.get("path", ""))
        incoming = spoke_path / "WAI-Spoke" / "lugs" / "incoming"
        if not incoming.exists():
            skipped_spokes.append(spoke.get("wheel_id", str(spoke_path)))
            continue
        dest = incoming / teaching_path.name
        dest.write_text(json.dumps(data, indent=2) + "\n")
        delivered_to.append(spoke.get("wheel_id", str(spoke_path)))

    return {
        "ok": True,
        "teaching_id": data.get("id", teaching_path.stem),
        "priority": priority,
        "delivered_to": delivered_to,
        "skipped_spokes": skipped_spokes,
    }


def _main(argv: list[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Teaching delivery cut tool")
    p.add_argument("command", choices=["check", "cut", "auto", "hot-patch"])
    p.add_argument("--hub-path", default=DEFAULT_HUB_PATH)
    p.add_argument("--teaching", default=None, help="Path to teaching file (hot-patch only)")
    args = p.parse_args(argv)

    hub_path = Path(args.hub_path)
    cmd = args.command

    if cmd == "check":
        result = check(hub_path)
    elif cmd == "cut":
        result = cut(hub_path)
    elif cmd == "auto":
        result = auto(hub_path)
    elif cmd == "hot-patch":
        if not args.teaching:
            print("ERROR: --teaching required for hot-patch command", file=sys.stderr)
            return 2
        result = deliver_hot_patch(Path(args.teaching), hub_path)
        if not result.get("ok"):
            for e in result.get("errors", []):
                print(f"ERROR: {e}", file=sys.stderr)
            return 1
    else:
        return 2

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
