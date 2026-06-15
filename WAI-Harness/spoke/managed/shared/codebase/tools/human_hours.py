#!/usr/bin/env python3
"""Calculate human hours spent on this project from session tracks.

Usage:
    python3 tools/human_hours.py [--detail]

Reads all session tracks, calculates duration per session from first/last
timestamp, and produces a summary with milestones.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

SPOKE = Path(__file__).parent.parent / "WAI-Spoke"
SESSIONS = SPOKE / "sessions"
_p = argparse.ArgumentParser(description="Calculate human hours spent from session tracks.")
_p.add_argument("--detail", action="store_true", help="Show per-session breakdown")
DETAIL = _p.parse_args().detail


def parse_ts(ts_str: str) -> datetime | None:
    """Parse ISO-8601 timestamp."""
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S+00:00"):
        try:
            return datetime.strptime(ts_str.replace("+00:00", "Z"), "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return None


def scan_sessions() -> list[dict]:
    """Scan all session tracks and compute durations."""
    results = []
    for session_dir in sorted(SESSIONS.iterdir()):
        if not session_dir.is_dir() or not session_dir.name.startswith("session-"):
            continue
        track = session_dir / "track.jsonl"
        if not track.exists():
            continue

        lines = [l.strip() for l in track.read_text().splitlines() if l.strip()]
        if not lines:
            continue

        turns = []
        milestones = []
        for line in lines:
            try:
                point = json.loads(line)
                ts = parse_ts(point.get("ts", ""))
                if ts:
                    turns.append({"ts": ts, "point": point})
                # Track milestones (decisions and completed items)
                for d in point.get("decisions", []):
                    milestones.append(d[:80])
            except json.JSONDecodeError:
                continue

        if len(turns) < 1:
            continue

        first_ts = turns[0]["ts"]
        last_ts = turns[-1]["ts"]
        duration = (last_ts - first_ts).total_seconds()

        results.append({
            "session": session_dir.name,
            "date": first_ts.strftime("%Y-%m-%d"),
            "turns": len(turns),
            "duration_seconds": duration,
            "duration_hours": round(duration / 3600, 2),
            "milestones": milestones[:5],  # top 5
        })

    return results


def main():
    sessions = scan_sessions()

    total_hours = sum(s["duration_hours"] for s in sessions)
    total_turns = sum(s["turns"] for s in sessions)
    total_sessions = len(sessions)

    print(f"\n{'='*60}")
    print(f"  Human Hours — {SPOKE.parent.name}")
    print(f"{'='*60}\n")
    print(f"  Sessions tracked:  {total_sessions}")
    print(f"  Total turns:       {total_turns}")
    print(f"  Total hours:       {total_hours:.1f}h")
    if total_sessions > 0:
        print(f"  Avg per session:   {total_hours/total_sessions:.1f}h")
        print(f"  Avg turns/session: {total_turns/total_sessions:.0f}")

    if DETAIL and sessions:
        print(f"\n  {'Session':<30} {'Date':<12} {'Turns':>5} {'Hours':>6}")
        print(f"  {'─'*30} {'─'*12} {'─'*5} {'─'*6}")
        for s in sessions:
            print(f"  {s['session']:<30} {s['date']:<12} {s['turns']:>5} {s['duration_hours']:>6.1f}")
            if s["milestones"]:
                for m in s["milestones"][:2]:
                    print(f"    → {m}")

    # Milestone timeline
    if sessions:
        print(f"\n  Timeline:")
        for s in sessions[-10:]:  # last 10
            bar = "█" * max(1, int(s["duration_hours"] * 4))
            print(f"  {s['date']} {bar} {s['duration_hours']:.1f}h ({s['turns']} turns)")

    print()


if __name__ == "__main__":
    main()
