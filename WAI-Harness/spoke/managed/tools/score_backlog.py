#!/usr/bin/env python3
"""Score active lugs by ROI with vibe-aware tiebreaking and cluster detection.

Usage:
    python3 tools/score_backlog.py [vibe] [--clusters] [--update-state]

Where vibe is one of: build, fix, think, grind, ship, refine
Default: no vibe filter (pure ROI ordering).

--clusters   Group related lugs into batch clusters for efficient dispatch.
--update-state  Write top items back to WAI-State.json _work_queue.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Path resolution: 1. ENV, 2. wai_paths base (v4 local / v3 WAI-Spoke), 3. v3 fallback
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wai_paths import resolve_wai_root  # noqa: E402  (v3/v4 resolver)


def _spoke_base() -> Path:
    if os.environ.get("WAI_SPOKE_PATH"):
        return Path(os.environ["WAI_SPOKE_PATH"])
    # Spoke repo root: tools/ -> managed -> spoke -> WAI-Harness -> ROOT
    repo_root = Path.cwd() if (Path.cwd() / "WAI-Harness").exists() else Path(__file__).resolve().parents[4]
    root, mode = resolve_wai_root(str(repo_root))
    if root and mode != "none":
        return Path(root)  # WAI-Harness/spoke/local on a v4 spoke
    return repo_root / "WAI-Spoke"  # last-resort v3 fallback


SPOKE = _spoke_base()

BYTYPE = SPOKE / "lugs" / "bytype"

# Failure threshold before autopilot treats a lug as stalled.
# Keep in sync with ozi_autopilot.OziAutopilot.AUTOPILOT_STALL_THRESHOLD
AUTOPILOT_STALL_THRESHOLD = 2

# Import shared lug utilities
sys.path.insert(0, str(Path(__file__).parent))
from lug_utils import is_blocked, blocked_reason, evaluate_execute_when, load_phases_from_state

# Vibe affinity: maps vibe -> type/tag -> bonus (0.0 to 1.0 added to ROI)
# Vibe affinity: multiplier applied to base ROI (1.0 = neutral)
# Values >1.0 boost, <1.0 suppress. This is multiplicative so it
# actually reorders items rather than adding tiny flat bonuses.
VIBE_AFFINITY = {
    "build": {
        "feature": 1.6, "epic": 1.3, "task": 1.0,
        "bug": 0.6, "signal": 0.5, "other": 0.8,
    },
    "fix": {
        "bug": 1.8, "task": 1.1, "feature": 0.7,
        "epic": 0.6, "signal": 0.8, "other": 0.9,
    },
    "think": {
        "epic": 1.6, "signal": 1.3, "feature": 1.2,
        "task": 0.7, "bug": 0.6, "other": 1.1,
    },
    "grind": {
        "task": 1.4, "signal": 1.2, "bug": 1.1,
        "feature": 0.6, "epic": 0.5, "other": 1.3,
    },
    "ship": {
        "in_progress": 1.8,  # strong bonus for anything already started
        "bug": 1.2, "task": 1.1, "feature": 1.1,
        "epic": 0.7, "signal": 0.6, "other": 0.9,
    },
    "refine": {
        "other": 1.4,      # ideas/decisions/policies need triage
        "feature": 1.3,    # lug quality and PEV gaps
        "implementation": 1.2,  # schema/spec completeness
        "epic": 0.7,       # epics are outcomes, not refinement targets
        "bug": 0.6,        # bugs are fix work, not refine work
        "signal": 0.5,     # signals route, don't refine
    },
}

# Default impact/effort by type when lug doesn't specify
TYPE_DEFAULTS = {
    "bug": {"impact": 6, "effort": 2},
    "task": {"impact": 5, "effort": 2},
    "feature": {"impact": 7, "effort": 3},
    "epic": {"impact": 8, "effort": 4},
    "signal": {"impact": 5, "effort": 1},
    "other": {"impact": 3, "effort": 1},
}


def classify_readiness(lug: dict, blocked: bool, lug_type: str = "") -> str:
    """Classify lug dispatch readiness: ready / needs_refinement / blocked / stalled."""
    # Stalled check first — autopilot failure gate takes priority over blocked
    lug_failures = (lug.get("workflow") or {}).get("autopilot_failures", 0)
    if lug_failures >= AUTOPILOT_STALL_THRESHOLD:
        return "stalled"
    if blocked:
        return "blocked"
    # Signals are patch alerts — they surface in Teachings & Signals, never refinement
    effective_type = lug_type or lug.get("type", "")
    if effective_type == "signal":
        return "ready"
    if effective_type == "epic":
        return "ready"
    # PEV completeness: has perceive + execute + verify, or acceptance_criteria
    has_perceive = bool(lug.get("perceive"))
    has_execute = bool(lug.get("execute"))
    has_verify = bool(lug.get("verify") or lug.get("acceptance_criteria"))
    if has_perceive and has_execute and has_verify:
        return "ready"
    return "needs_refinement"


def infer_leverage(lug: dict) -> float:
    """Estimate leverage multiplier from lug content."""
    text = json.dumps(lug).lower()
    # Multi-phase continuation: lug had prior-phase blockers that are now all cleared.
    # Prioritise finishing in-flight phased work over context-switching to new threads.
    blocked_by = lug.get("blocked_by", [])
    if blocked_by and not is_blocked(lug):
        return 1.6
    # Foundational items that unblock others
    if any(kw in text for kw in ["foundational", "unblocks", "prerequisite", "schema", "bootstrap"]):
        return 1.5
    # Items with children or dependents
    if "children" in lug or "blocks" in text:
        return 1.5
    # In-progress items (momentum)
    if lug.get("s") in ("in_progress", "in-progress", "p"):
        return 1.3
    return 1.0


def score_lug(lug: dict, lug_type: str, status: str, vibe: str | None = None) -> float:
    """Calculate ROI score with optional vibe tiebreaking."""
    defaults = TYPE_DEFAULTS.get(lug_type, TYPE_DEFAULTS["other"])
    raw_impact = lug.get("impact", defaults["impact"])
    raw_effort = lug.get("effort", defaults["effort"])
    try:
        impact = float(raw_impact)
    except (TypeError, ValueError):
        impact = float(defaults["impact"])
    try:
        effort = float(raw_effort)
    except (TypeError, ValueError):
        effort = float(defaults["effort"])
    leverage = infer_leverage(lug)

    # Base ROI
    # Signals are routing chores, not implementation — cap their ROI
    # so they don't crowd out real work
    if lug_type == "signal":
        roi = min(impact * 0.5, 5.0)  # cap at 5.0, scaled down
    else:
        roi = (impact * leverage) / max(effort, 0.5)

    # Vibe multiplier — reshapes ordering to match energy
    if vibe and vibe in VIBE_AFFINITY:
        affinity = VIBE_AFFINITY[vibe]
        multiplier = affinity.get(lug_type, 1.0)
        # Ship vibe: extra boost for in-progress items (finish what's started)
        if vibe == "ship" and status in ("in_progress", "in-progress"):
            multiplier *= affinity.get("in_progress", 1.0)
        roi *= multiplier

    return round(roi, 2)


TYPE_PREFIXES = (
    "feature-", "impl-", "implementation-", "epic-", "bug-",
    "task-", "idea-", "lug-", "policy-", "decision-",
)
VERSION_SUFFIXES = ("-v1", "-v2", "-v3", "-v4", "-v5")


def extract_cluster_key(lug: dict, lug_id: str) -> str:
    """Extract a cluster key from a lug — shared key = batch together."""
    # Epic membership takes priority
    epic_id = lug.get("epic_id") or lug.get("parent_epic")
    if epic_id:
        return f"epic:{epic_id}"

    # Strip type prefix
    key = lug_id
    for prefix in TYPE_PREFIXES:
        if key.startswith(prefix):
            key = key[len(prefix):]
            break

    # Strip version/date suffix
    for suffix in VERSION_SUFFIXES:
        if key.endswith(suffix):
            key = key[: -len(suffix)]
            break
    # Strip 8-digit date suffix (e.g. 20260330)
    import re
    key = re.sub(r"-\d{8}$", "", key)

    # Take first 2 hyphen-separated words as domain key
    parts = key.split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else key


def build_clusters(scored: list[dict]) -> list[dict]:
    """Group related lugs into clusters for batch dispatch.

    Returns a list of cluster dicts:
      {"key": str, "items": [scored...], "roi": float, "solo": bool}
    solo=True means single-member group (no real cluster).
    """
    from collections import defaultdict

    groups: dict[str, list] = defaultdict(list)
    for item in scored:
        lug_id = item["lug"].get("id") or item["lug"].get("i") or item["file"].replace(".json", "")
        key = extract_cluster_key(item["lug"], lug_id)
        groups[key].append(item)

    clusters = []
    for key, items in groups.items():
        clusters.append({
            "key": key,
            "items": items,
            "roi": max(i["roi"] for i in items),
            "solo": len(items) == 1,
        })

    # Sort clusters by their max ROI descending
    clusters.sort(key=lambda c: c["roi"], reverse=True)
    return clusters


def scan_active_lugs() -> list[dict]:
    """Scan bytype/ for open and in_progress lugs."""
    results = []
    for type_dir in sorted(BYTYPE.iterdir()):
        if not type_dir.is_dir():
            continue
        lug_type = type_dir.name
        if lug_type == "signal":
            continue  # signals are in WAI-Spoke/signals/ (v2), not bytype/
        for status_dir in ["open", "in_progress"]:
            # "undelivered" removed: signals moved to WAI-Spoke/signals/ (v2 architecture)
            status_path = type_dir / status_dir
            if not status_path.exists():
                continue
            for lug_file in sorted(status_path.glob("*.json")):
                try:
                    lug = json.loads(lug_file.read_text())
                    results.append({
                        "file": lug_file.name,
                        "type": lug_type,
                        "status": status_dir,
                        "title": lug.get("t", lug.get("title", lug_file.stem)),
                        "impact": lug.get("impact"),
                        "effort": lug.get("effort"),
                        "lug": lug,
                    })
                except (json.JSONDecodeError, OSError) as e:
                    print(f"  SKIP {lug_file.name}: {e}", file=sys.stderr)
    return results


def update_state_work_queue(scored: list[dict], phases: list[dict]) -> None:
    """Write top items back to WAI-State.json _work_queue."""
    state_file = SPOKE / "WAI-State.json"
    if not state_file.exists():
        return
    try:
        state = json.loads(state_file.read_text())
    except (json.JSONDecodeError, OSError):
        return

    wq = state.setdefault("_work_queue", {"enabled": True})

    # Count stalled from the FULL scored list (not just top-15) for accuracy
    stalled_count = sum(
        1 for entry in scored
        if classify_readiness(entry["lug"], entry.get("_blocked", False), entry["type"]) == "stalled"
    )

    # Include top items (up to 15), classify readiness
    items = []
    ready_count = 0
    needs_refinement_count = 0
    blocked_count = 0
    for entry in scored[:15]:
        readiness = classify_readiness(
            entry["lug"],
            entry.get("_blocked", False),
            lug_type=entry["type"],
        )
        # Gated items are blocked from dispatch perspective
        if entry.get("_gated"):
            readiness = "blocked"
        if readiness == "ready":
            ready_count += 1
        elif readiness == "needs_refinement":
            needs_refinement_count += 1
        elif readiness == "stalled":
            pass  # already counted above from full list
        else:
            blocked_count += 1
        items.append({
            "id": entry["lug"].get("id", entry["file"].replace(".json", "")),
            "roi": entry["roi"],
            "type": entry["type"],
            "status": "ready" if not (entry.get("_blocked") or entry.get("_gated")) else "gated",
            "readiness": readiness,
            "title": entry["title"][:80],
            "phase": entry["lug"].get("phase"),
            "tagged_next": len(items) == 0 and readiness == "ready",
            "has_estimated_seconds": bool(entry["lug"].get("estimated_seconds")),
        })
        if len(items) >= 15:
            break

    wq["items"] = items
    wq["queue_state"] = {
        "ready_count": ready_count,
        "needs_refinement_count": needs_refinement_count,
        "blocked_count": blocked_count,
        "stalled_count": stalled_count,
    }
    wq["last_scored_at"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()
    if phases:
        wq["phases"] = phases

    state_file.write_text(json.dumps(state, indent=2) + "\n")
    print(
        f"\n  ✅ _work_queue updated ({len(items)} items: {ready_count} ready, "
        f"{needs_refinement_count} needs_refinement, {blocked_count} blocked, "
        f"{stalled_count} stalled)\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Score active lugs by ROI with vibe-aware tiebreaking.")
    parser.add_argument("vibe", nargs="?", choices=list(VIBE_AFFINITY.keys()), metavar="VIBE",
                        help=f"Optional vibe filter: {', '.join(VIBE_AFFINITY.keys())}")
    parser.add_argument("--clusters", action="store_true", help="Group related lugs into batch clusters")
    parser.add_argument("--update-state", action="store_true", help="Write scored queue back to WAI-State.json")
    args = parser.parse_args()
    update_state = args.update_state
    show_clusters = args.clusters
    vibe = args.vibe

    phases = load_phases_from_state()
    lugs = scan_active_lugs()
    scored = []
    for entry in lugs:
        roi = score_lug(entry["lug"], entry["type"], entry["status"], vibe)
        # Check blocking/gating
        ready, gate_reason = evaluate_execute_when(entry["lug"], phases)
        scored.append({
            **entry,
            "roi": roi,
            "_blocked": is_blocked(entry["lug"]),
            "_gated": not ready,
            "_gate_reason": gate_reason,
        })

    # Extract urgency tier (1-5, default 3 = NORMAL)
    for entry in scored:
        try:
            entry["_urgency"] = int(entry["lug"].get("urgency", 3))
        except (TypeError, ValueError):
            entry["_urgency"] = 3

    # Sort: urgency tier ascending (1=first), then ROI descending within tier
    scored.sort(key=lambda x: (x["_urgency"], -x["roi"]))

    # Partition into dispatchable and gated
    dispatchable = [s for s in scored if not s["_gated"]]
    gated = [s for s in scored if s["_gated"]]

    # Display dispatchable items
    vibe_label = f" | Vibe: {vibe}" if vibe else ""
    print(f"\n{'='*80}")
    print(f"  Ozi ROI Backlog — {len(dispatchable)} ready, {len(gated)} gated{vibe_label}")
    print(f"{'='*80}\n")

    if show_clusters:
        clusters = build_clusters(dispatchable)
        slot = 0
        for cluster in clusters:
            if slot >= 10:
                remaining = len(clusters) - clusters.index(cluster)
                print(f"\n  ... and {remaining} more clusters\n")
                break
            if cluster["solo"]:
                item = cluster["items"][0]
                phase_tag = f" [{item['lug'].get('phase', '')}]" if item["lug"].get("phase") else ""
                print(f"  {slot+1:>3}  {item['roi']:>5.1f}  {item['type']:<10} {item['status']:<13} {item['title'][:55]}{phase_tag}")
                slot += 1
            else:
                count = len(cluster["items"])
                print(f"  {slot+1:>3}  {cluster['roi']:>5.1f}  [batch x{count}]    ── {cluster['key']}")
                for item in cluster["items"]:
                    phase_tag = f" [{item['lug'].get('phase', '')}]" if item["lug"].get("phase") else ""
                    print(f"       {'':>5}  {'':10} {'':13}   • {item['title'][:52]}{phase_tag}")
                slot += 1
    else:
        TIER_LABELS = {1: "URGENT", 2: "HIGH", 3: "NORMAL", 4: "LOW", 5: "DEFER"}
        print(f"  {'#':>3}  {'ROI':>5}  {'Type':<10} {'Status':<13} {'Title'}")
        print(f"  {'─'*3}  {'─'*5}  {'─'*10} {'─'*13} {'─'*40}")
        current_tier = None
        for i, item in enumerate(dispatchable, 1):
            tier = item.get("_urgency", 3)
            if tier != current_tier:
                current_tier = tier
                label = TIER_LABELS.get(tier, f"TIER{tier}")
                if tier != 3:  # only show band header for non-default tiers
                    print(f"\n  ── {label} ──")
            phase_tag = f" [{item['lug'].get('phase', '')}]" if item["lug"].get("phase") else ""
            print(f"  {i:>3}  {item['roi']:>5.1f}  {item['type']:<10} {item['status']:<13} {item['title'][:60]}{phase_tag}")
            if i == 10 and len(dispatchable) > 10:
                print(f"\n  ... and {len(dispatchable) - 10} more ready items\n")
                break

    # Display gated items
    if gated:
        print(f"\n  {'─'*78}")
        print(f"  GATED ({len(gated)} items — waiting on conditions)")
        print(f"  {'─'*78}")
        for item in gated[:5]:
            reason = item["_gate_reason"][:50] if item["_gate_reason"] else "unknown"
            print(f"  🔒 {item['roi']:>5.1f}  {item['type']:<10} {item['title'][:45]}  ← {reason}")
        if len(gated) > 5:
            print(f"  ... and {len(gated) - 5} more gated items")

    # Summary by type
    print(f"\n  {'Type':<12} {'Count':>5}  {'Avg ROI':>7}  {'Best':>5}")
    print(f"  {'─'*12} {'─'*5}  {'─'*7}  {'─'*5}")
    types: dict[str, list[float]] = {}
    for item in scored:
        t = item["type"]
        if t not in types:
            types[t] = []
        types[t].append(item["roi"])
    for t in sorted(types, key=lambda x: -(sum(types[x]) / len(types[x]))):
        vals = types[t]
        print(f"  {t:<12} {len(vals):>5}  {sum(vals)/len(vals):>7.1f}  {max(vals):>5.1f}")

    print()

    if update_state:
        update_state_work_queue(scored, phases)


if __name__ == "__main__":
    main()
