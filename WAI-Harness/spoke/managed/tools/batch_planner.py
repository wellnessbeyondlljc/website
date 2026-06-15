#!/usr/bin/env python3
"""Batch planner: groups ready lugs into collision-safe parallel batches.

Usage:
    python3 tools/batch_planner.py [--all-open] [--json]

Without flags: loads 'ready' lugs from _work_queue in WAI-State.json.
--all-open: loads all open lugs from bytype/ directly.
--json: always output JSON (default when piped, summary otherwise).
Output: JSON to stdout with BATCH_SCHEMA.

BATCH_SCHEMA:
{
  "batches": [
    {
      "batch_number": 1,
      "items": ["lug-id-a", "lug-id-b"],
      "parallel": true,
      "collision_free": true
    }
  ],
  "collision_pairs": [["lug-id-x", "lug-id-y"]],
  "ready_count": 3,
  "generated_at": "ISO8601"
}
"""

import argparse
import json
import sys
import os
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _normalize_target_file(tf: str) -> str:
    """Strip inline comments from target_file entries: 'foo.py (new)' -> 'foo.py'."""
    return tf.split(" ")[0].strip()


def _spoke_paths(spoke_root: Optional[Path]) -> tuple[Path, Path]:
    """Return (bytype_dir, state_file) for the given spoke root (or cwd)."""
    root = spoke_root if spoke_root is not None else Path.cwd()
    spoke = root / "WAI-Spoke"
    return spoke / "lugs" / "bytype", spoke / "WAI-State.json"


def load_ready_lugs(all_open: bool = False, spoke_root: Optional[Path] = None) -> list[dict]:
    """Load ready lugs: from _work_queue (default) or all open lugs (--all-open).

    Args:
        all_open: If True, load all open/in_progress lugs from bytype/ directly.
        spoke_root: Path to the project root that contains WAI-Spoke/. Defaults to cwd.
    """
    bytype, state = _spoke_paths(spoke_root)
    if all_open:
        return _load_all_open(bytype)
    return _load_from_work_queue(state, bytype)


def _load_all_open(bytype: Path) -> list[dict]:
    """Scan bytype/*/open/*.json and bytype/*/in_progress/*.json."""
    results = []
    if not bytype.exists():
        return results
    for type_dir in sorted(bytype.iterdir()):
        if not type_dir.is_dir():
            continue
        for status in ("open", "in_progress"):
            sd = type_dir / status
            if not sd.exists():
                continue
            for lug_file in sorted(sd.glob("*.json")):
                try:
                    lug = json.loads(lug_file.read_text())
                    lug_id = lug.get("id") or lug.get("i") or lug_file.stem
                    results.append({
                        "id": lug_id,
                        "title": lug.get("title") or lug.get("t") or lug_id,
                        "target_files": lug.get("target_files", []),
                        "blocked_by": lug.get("blocked_by", []),
                        "roi": lug.get("roi", 0),
                    })
                except (json.JSONDecodeError, OSError):
                    pass
    return results


def _load_from_work_queue(state: Path, bytype: Path) -> list[dict]:
    """Load ready items from WAI-State.json _work_queue."""
    if not state.exists():
        return []
    try:
        state_data = json.loads(state.read_text())
    except (json.JSONDecodeError, OSError):
        return []

    items = state_data.get("_work_queue", {}).get("items", [])
    ready = [item for item in items if item.get("readiness") == "ready"]

    results = []
    for item in ready:
        lug_id = item.get("id", "")
        # Try to load full lug for target_files and blocked_by
        full_lug = _resolve_lug(lug_id, bytype)
        results.append({
            "id": lug_id,
            "title": item.get("title", lug_id),
            "target_files": full_lug.get("target_files", []) if full_lug else [],
            "blocked_by": full_lug.get("blocked_by", []) if full_lug else [],
            "roi": item.get("roi", 0),
        })
    return results


def _resolve_lug(lug_id: str, bytype: Path) -> dict | None:
    """Find a lug file across all bytype/ folders and return its content."""
    if not bytype.exists():
        return None
    for type_dir in bytype.iterdir():
        if not type_dir.is_dir():
            continue
        for status_dir in type_dir.iterdir():
            if not status_dir.is_dir():
                continue
            candidate = status_dir / f"{lug_id}.json"
            if candidate.exists():
                try:
                    return json.loads(candidate.read_text())
                except (json.JSONDecodeError, OSError):
                    return None
    return None


def detect_collisions(lugs: list[dict], spoke_root: Optional[Path] = None) -> list[tuple[str, str]]:
    """Return list of (lug_id_a, lug_id_b) pairs sharing any target_file.

    Args:
        lugs: List of lug dicts (already loaded).
        spoke_root: Accepted for API parity with load_ready_lugs; not used internally.
    """
    file_to_lugs: dict[str, list[str]] = defaultdict(list)
    for lug in lugs:
        lug_id = lug["id"]
        for tf in lug.get("target_files", []):
            key = _normalize_target_file(tf)
            if key:
                file_to_lugs[key].append(lug_id)

    collision_pairs = set()
    for lug_ids in file_to_lugs.values():
        if len(lug_ids) > 1:
            for i in range(len(lug_ids)):
                for j in range(i + 1, len(lug_ids)):
                    pair = tuple(sorted([lug_ids[i], lug_ids[j]]))
                    collision_pairs.add(pair)
    return list(collision_pairs)


def topo_sort_lugs(lugs: list[dict], collision_pairs: list[tuple[str, str]]) -> list[list[str]]:
    """Group lugs into ordered batches using Kahn's algorithm.

    blocked_by edges plus collision pairs both act as ordering constraints.
    Collision pairs are mutual: a and b cannot be in the same batch.
    """
    lug_ids = {lug["id"] for lug in lugs}
    id_to_lug = {lug["id"]: lug for lug in lugs}

    # Build adjacency: prerequisite_id -> set of lug_ids that must come after it
    must_come_after: dict[str, set[str]] = defaultdict(set)
    # Build in-degree: lug_id -> count of unresolved prerequisites
    in_degree: dict[str, int] = {lug_id: 0 for lug_id in lug_ids}

    # blocked_by edges
    for lug in lugs:
        for blocker in lug.get("blocked_by", []):
            if blocker in lug_ids:
                must_come_after[blocker].add(lug["id"])
                in_degree[lug["id"]] += 1

    # Kahn's algorithm: batch = all nodes with in_degree 0
    batches = []
    remaining = set(lug_ids)

    while remaining:
        # Find all nodes with no remaining prerequisites in this round
        current_batch = {lid for lid in remaining if in_degree[lid] == 0}
        if not current_batch:
            # Cycle detected — put remaining items in one final batch
            current_batch = remaining.copy()

        # Respect collision pairs: if two colliding lugs are in the same batch,
        # defer the lower-ROI one to the next batch
        collision_map: dict[str, set[str]] = defaultdict(set)
        for (a, b) in collision_pairs:
            if a in current_batch and b in current_batch:
                collision_map[a].add(b)
                collision_map[b].add(a)

        final_batch: list[str] = []
        deferred: set[str] = set()
        for lid in sorted(current_batch, key=lambda x: -id_to_lug[x].get("roi", 0)):
            if lid in deferred:
                continue
            final_batch.append(lid)
            # Defer all colliders
            for collider in collision_map.get(lid, set()):
                deferred.add(collider)

        batches.append(final_batch)

        # Reduce in-degrees for the next round
        for lid in final_batch:
            for successor in must_come_after.get(lid, set()):
                if successor in remaining:
                    in_degree[successor] -= 1

        remaining -= set(final_batch)
        remaining -= deferred
        # Re-add deferred to remaining for next iteration (in_degree already correct)
        remaining |= deferred

        # Avoid infinite loop if deferred never clears
        if not final_batch:
            batches.append(list(remaining))
            break

    return [b for b in batches if b]


def build_output(lugs: list[dict], batches: list[list[str]], collision_pairs: list[tuple[str, str]]) -> dict:
    """Build the final JSON output."""
    batch_list = []
    for i, batch_items in enumerate(batches, start=1):
        # Check if batch is internally collision-free
        batch_set = set(batch_items)
        intra_collisions = [
            [a, b] for (a, b) in collision_pairs
            if a in batch_set and b in batch_set
        ]
        batch_list.append({
            "batch_number": i,
            "items": sorted(batch_items),
            "parallel": len(batch_items) > 1,
            "collision_free": len(intra_collisions) == 0,
        })

    return {
        "batches": batch_list,
        "collision_pairs": [list(p) for p in collision_pairs],
        "ready_count": len(lugs),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch planner: groups ready lugs into collision-safe parallel batches.")
    parser.add_argument("--all-open", action="store_true", help="Load all open lugs instead of work queue")
    parser.add_argument("--json", action="store_true", help="Always output JSON (default when piped)")
    args = parser.parse_args()
    all_open = args.all_open
    json_output = args.json or not sys.stdout.isatty()

    lugs = load_ready_lugs(all_open=all_open)

    if not lugs:
        if json_output:
            print(json.dumps({"batches": [], "collision_pairs": [], "ready_count": 0, "generated_at": datetime.now(timezone.utc).isoformat()}, indent=2))
        else:
            print("No ready items for parallel dispatch.")
        return

    collision_pairs = detect_collisions(lugs)
    batches = topo_sort_lugs(lugs, collision_pairs)
    output = build_output(lugs, batches, collision_pairs)

    if json_output:
        print(json.dumps(output, indent=2))
    else:
        print(f"Batch plan: {output['ready_count']} items in {len(output['batches'])} batch(es)")
        for b in output["batches"]:
            parallel = "parallel" if b["parallel"] else "sequential"
            print(f"  Batch {b['batch_number']} ({len(b['items'])} items, {parallel}): {', '.join(b['items'])}")
        if output["collision_pairs"]:
            print(f"  Collision pairs: {output['collision_pairs']}")


if __name__ == "__main__":
    main()
