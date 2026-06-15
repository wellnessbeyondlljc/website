#!/usr/bin/env python3
"""Lathe Portfolio Scorer — combines strategic weights with gardener health and attention data.

Usage:
    python3 tools/lathe_score.py [--hub-path PATH]
"""

import argparse
import json
import os
import sys
from pathlib import Path

_p = argparse.ArgumentParser(description="Lathe Portfolio Scorer — combines strategic weights with gardener health and attention data.")
_p.add_argument("--hub-path", default=os.environ.get("WAI_HUB_PATH", ""), metavar="PATH", help="Path to hub root")
HUB_PATH = Path(_p.parse_args().hub_path)
LATHE_CONFIG = HUB_PATH / "WAI-Hub/advisors/lathe/spoke_lathe.json"


# Shift direction weights (how much investment this direction demands)
SHIFT_WEIGHTS = {
    "growth": 1.5,
    "revenue": 2.0,
    "research": 0.8,
    "maintain": 0.5,
    "sunset": 0.1,
}


def load_registry():
    """Load hub spoke registry."""
    reg_path = HUB_PATH / "WAI-Hub/registry/hub-registry.json"
    if reg_path.exists():
        return json.loads(reg_path.read_text())
    # Fallback: scan incoming
    incoming = HUB_PATH / "WAI-Hub/registry/incoming"
    if incoming.exists():
        spokes = {}
        for f in incoming.glob("*.json"):
            try:
                spokes[f.stem] = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return spokes
    return {}


def load_lathe_config():
    """Load lathe portfolio config."""
    if LATHE_CONFIG.exists():
        return json.loads(LATHE_CONFIG.read_text())
    return {"spokes": {}}


def score_spoke(spoke_id, spoke_data, lathe_spokes):
    """Score a spoke: shift_weight * recency * session_activity."""
    lathe = lathe_spokes.get(spoke_id, {})
    shift = lathe.get("shift_direction", "maintain")
    shift_weight = SHIFT_WEIGHTS.get(shift, 0.5)

    # Recency: sessions in last 7 days boost score
    session_count = spoke_data.get("session_count", 0)

    # Base score
    score = shift_weight * max(1, session_count ** 0.3)  # diminishing returns on session count

    return {
        "spoke_id": spoke_id,
        "name": spoke_data.get("name", spoke_id),
        "shift": shift,
        "shift_weight": shift_weight,
        "sessions": session_count,
        "score": round(score, 2),
        "budget": lathe.get("budget", {}),
    }


def main():
    config = load_lathe_config()
    registry = load_registry()

    scored = []
    for spoke_id, spoke_data in registry.items():
        result = score_spoke(spoke_id, spoke_data, config.get("spokes", {}))
        scored.append(result)

    scored.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n{'='*60}")
    print(f"  Lathe Portfolio — {len(scored)} spokes")
    print(f"{'='*60}\n")
    print(f"  {'#':>3}  {'Score':>5}  {'Shift':<10} {'Sessions':>8}  {'Name'}")
    print(f"  {'─'*3}  {'─'*5}  {'─'*10} {'─'*8}  {'─'*30}")

    for i, s in enumerate(scored, 1):
        print(f"  {i:>3}  {s['score']:>5.1f}  {s['shift']:<10} {s['sessions']:>8}  {s['name']}")

    # Summary by shift direction
    print(f"\n  Allocation by shift:")
    shifts = {}
    for s in scored:
        d = s["shift"]
        if d not in shifts:
            shifts[d] = []
        shifts[d].append(s)
    for d in sorted(shifts, key=lambda x: -SHIFT_WEIGHTS.get(x, 0)):
        count = len(shifts[d])
        total_score = sum(s["score"] for s in shifts[d])
        print(f"  {d:<12} {count} spokes, total score {total_score:.1f}")

    print()


if __name__ == "__main__":
    main()
