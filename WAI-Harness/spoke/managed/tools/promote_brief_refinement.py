#!/usr/bin/env python3
"""
promote_brief_refinement.py — Promote Ozi brief refinements after 3 occurrences.

Review refinements.jsonl and apply those with occurrences >= 3.

Usage:
    python3 tools/promote_brief_refinement.py
    python3 tools/promote_brief_refinement.py --dry-run
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict

SPOKE_PATH = Path(__file__).parent.parent / "WAI-Spoke"
REFINEMENTS_PATH = SPOKE_PATH / "advisors" / "ozi" / "refinements.jsonl"
SCAN_STATE_PATH = SPOKE_PATH / "advisors" / "ozi" / "scan_state.json"
PROMOTION_THRESHOLD = 3


def load_refinements() -> List[Dict]:
    if not REFINEMENTS_PATH.exists():
        return []

    refinements = []
    with open(REFINEMENTS_PATH) as f:
        for line in f:
            if line.strip():
                refinements.append(json.loads(line))

    return refinements


def group_by_proposal(refinements: List[Dict]) -> Dict[str, List[Dict]]:
    groups = {}
    for ref in refinements:
        key = ref.get("proposed_adjustment", "unknown")
        if key not in groups:
            groups[key] = []
        groups[key].append(ref)

    return groups


def apply_refinement(refinement: Dict, dry_run: bool = False):
    if dry_run:
        print(f"    Would apply: {refinement['proposed_adjustment']}")
        print(f"      Evidence: {refinement['evidence'][:100]}...")
        return

    refinement["promotion_status"] = "promoted"
    refinement["promoted_at"] = datetime.now(timezone.utc).isoformat()

    print(f"    ✅ Applied: {refinement['proposed_adjustment']}")


def promote_refinements(dry_run: bool = False):
    refinements = load_refinements()

    if not refinements:
        print("No refinements found.")
        return

    groups = group_by_proposal(refinements)

    promoted_count = 0

    for proposal, group in groups.items():
        pending = [r for r in group if r.get("promotion_status") == "pending"]
        occurrences = len(pending)

        if occurrences >= PROMOTION_THRESHOLD:
            print(f"\n📋 Proposal: {proposal}")
            print(f"  Occurrences: {occurrences} (threshold: {PROMOTION_THRESHOLD})")
            print(f"  Evidence samples:")

            for ref in pending[:3]:
                evidence = ref.get("evidence", "no evidence")
                print(f"    - {evidence[:100]}...")

            apply_refinement(pending[0], dry_run)

            for ref in pending[1:]:
                ref["promotion_status"] = "duplicate"

            promoted_count += 1

    if not dry_run and promoted_count > 0:
        with open(REFINEMENTS_PATH, "w") as f:
            for ref in refinements:
                f.write(json.dumps(ref) + "\n")

        if SCAN_STATE_PATH.exists():
            with open(SCAN_STATE_PATH) as f:
                state = json.load(f)

            brief_gen = state.setdefault("brief_generation", {})
            promoted = brief_gen.get("refinements_promoted", 0) + promoted_count
            brief_gen["refinements_promoted"] = promoted

            with open(SCAN_STATE_PATH, "w") as f:
                json.dump(state, f, indent=2)

    print(
        f"\n{'Would promote' if dry_run else 'Promoted'}: {promoted_count} refinement(s)"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Promote brief refinements")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be promoted"
    )
    args = parser.parse_args()

    print("Ozi Brief Refinement Promotion")
    print("=" * 50)
    promote_refinements(dry_run=args.dry_run)
