#!/usr/bin/env python3
"""Enrich active lugs with missing buildability fields.

Adds PEV, acceptance_criteria, impact, and effort based on content analysis.
Only touches lugs that are missing these fields.

Usage:
    python3 tools/enrich_lugs.py [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path

_p = argparse.ArgumentParser(description="Enrich active lugs with missing buildability fields.")
_p.add_argument("--dry-run", action="store_true", help="Show changes, don't write")
DRY_RUN = _p.parse_args().dry_run
SPOKE = Path("WAI-Spoke")
BYTYPE = SPOKE / "lugs" / "bytype"

# Default effort by type
TYPE_EFFORT = {"epic": 4, "feature": 3, "task": 2, "bug": 2, "signal": 1, "other": 2}
TYPE_IMPACT = {"epic": 8, "feature": 7, "task": 5, "bug": 6, "signal": 8, "other": 4}


def infer_pev(lug):
    """Generate PEV from description and existing fields."""
    desc = lug.get("description", lug.get("t", lug.get("title", "")))
    title = lug.get("t", lug.get("title", ""))

    perceive = lug.get("perceive")
    if not perceive:
        perceive = f"Read the current state relevant to: {title[:80]}. Identify what exists, what's missing, and what needs to change."

    execute = lug.get("execute")
    if not execute:
        if desc:
            execute = f"Implement: {desc[:200]}"
        else:
            execute = f"Implement the changes described in: {title[:80]}"

    verify = lug.get("verify")
    if not verify:
        verify = f"Verify: the implementation matches the described intent. Test against project principles and mission goals."

    return perceive, execute, verify


def infer_acceptance_criteria(lug):
    """Generate acceptance criteria from description."""
    title = lug.get("t", lug.get("title", ""))
    desc = lug.get("description", "")

    criteria = []
    # Extract from existing fields
    if lug.get("acceptance_criteria"):
        return lug["acceptance_criteria"]

    if lug.get("acceptance"):
        return lug["acceptance"]

    # Generate from description
    criteria.append(f"Implementation matches described intent in: {title[:60]}")
    criteria.append("Changes verified against project principles and mission goals")
    criteria.append("No regressions in existing functionality")

    return criteria


def enrich(lug, lug_type):
    """Add missing fields to a lug."""
    changed = False

    # PEV
    if not lug.get("perceive") or not lug.get("execute") or not lug.get("verify"):
        p, e, v = infer_pev(lug)
        if not lug.get("perceive"):
            lug["perceive"] = p
            changed = True
        if not lug.get("execute"):
            lug["execute"] = e
            changed = True
        if not lug.get("verify"):
            lug["verify"] = v
            changed = True

    # Acceptance criteria
    if not lug.get("acceptance_criteria"):
        lug["acceptance_criteria"] = infer_acceptance_criteria(lug)
        changed = True

    # Impact
    if not lug.get("impact"):
        lug["impact"] = TYPE_IMPACT.get(lug_type, 5)
        changed = True

    # Effort
    if not lug.get("effort") and not lug.get("pev", {}).get("effort"):
        lug["effort"] = TYPE_EFFORT.get(lug_type, 2)
        changed = True

    return changed


def main():
    enriched = 0
    skipped = 0

    for type_dir in sorted(BYTYPE.iterdir()):
        if not type_dir.is_dir():
            continue
        lug_type = type_dir.name
        for status in ["open", "in_progress"]:
            status_dir = type_dir / status
            if not status_dir.exists():
                continue
            for f in sorted(status_dir.glob("*.json")):
                try:
                    lug = json.loads(f.read_text())
                except (json.JSONDecodeError, OSError):
                    continue

                if enrich(lug, lug_type):
                    if DRY_RUN:
                        print(f"  [DRY] {f.name}")
                    else:
                        f.write_text(json.dumps(lug, indent=2) + "\n")
                        print(f"  ENRICHED {f.name}")
                    enriched += 1
                else:
                    skipped += 1

    print(f"\n{'[DRY RUN] ' if DRY_RUN else ''}Enriched: {enriched}, Already complete: {skipped}")


if __name__ == "__main__":
    main()
