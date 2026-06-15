#!/usr/bin/env python3
"""Batch-tag active lugs with vibe_affinity based on type and content heuristics.

Usage:
    python3 tools/tag_vibe_affinity.py [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

SPOKE = Path(__file__).parent.parent / "WAI-Spoke"
BYTYPE = SPOKE / "lugs" / "bytype"

_p = argparse.ArgumentParser(description="Batch-tag active lugs with vibe_affinity based on type and content heuristics.")
_p.add_argument("--dry-run", action="store_true", help="Show changes, don't write")
DRY_RUN = _p.parse_args().dry_run

# Heuristic: map lug type to default vibe affinity
TYPE_TO_VIBE = {
    "bug": "fix",
    "feature": "build",
    "epic": "think",
    "signal": "think",
}

# Content keywords that override the type default
KEYWORD_OVERRIDES = {
    "grind": ["thrift", "batch", "cleanup", "audit", "routing", "mechanical", "slim"],
    "ship": ["finish", "close", "complete", "in_progress", "near-done"],
    "fix": ["bug", "broken", "dirty", "reliably", "threshold", "fix"],
    "build": ["new", "create", "design", "dashboard", "advisor", "portfolio"],
    "think": ["architecture", "decision", "strategy", "protocol", "design"],
}


def infer_vibe(lug: dict, lug_type: str) -> str:
    """Infer vibe_affinity from type and content."""
    # Already tagged? Skip.
    if lug.get("va") or lug.get("vibe_affinity"):
        return lug.get("va") or lug.get("vibe_affinity")

    text = json.dumps(lug).lower()

    # Check keyword overrides first (more specific than type)
    scores = {}
    for vibe, keywords in KEYWORD_OVERRIDES.items():
        scores[vibe] = sum(1 for kw in keywords if kw in text)

    # If a keyword vibe scores 2+, use it
    best_kw = max(scores, key=scores.get)
    if scores[best_kw] >= 2:
        return best_kw

    # Fall back to type default
    if lug_type == "task":
        # Tasks are ambiguous — check content
        if scores["grind"] >= 1:
            return "grind"
        if scores["build"] >= 1:
            return "build"
        return "grind"  # default tasks to grind

    return TYPE_TO_VIBE.get(lug_type, "grind")


def main():
    tagged = 0
    skipped = 0
    errors = 0

    for type_dir in sorted(BYTYPE.iterdir()):
        if not type_dir.is_dir():
            continue
        lug_type = type_dir.name
        for status_dir in ["open", "in_progress", "undelivered"]:
            status_path = type_dir / status_dir
            if not status_path.exists():
                continue
            for lug_file in sorted(status_path.glob("*.json")):
                try:
                    lug = json.loads(lug_file.read_text())
                except (json.JSONDecodeError, OSError) as e:
                    print(f"  ERROR {lug_file.name}: {e}")
                    errors += 1
                    continue

                # Skip if already tagged
                if lug.get("va") or lug.get("vibe_affinity"):
                    skipped += 1
                    continue

                vibe = infer_vibe(lug, lug_type)
                lug["va"] = vibe

                if DRY_RUN:
                    print(f"  [DRY] {lug_file.name} → {vibe}")
                else:
                    lug_file.write_text(json.dumps(lug, indent=2) + "\n")
                    print(f"  TAG   {lug_file.name} → {vibe}")
                tagged += 1

    print(f"\n{'[DRY RUN] ' if DRY_RUN else ''}Tagged: {tagged}, Skipped (already tagged): {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()
