#!/usr/bin/env python3
"""capgraph_monitor — observe the AP block-memory so it can DRIVE changes.

Reads the spoke-local antipattern store + blocks.jsonl event log and renders:
  - totals (antipatterns, occurrences, open/resolved)
  - counts by block_class
  - TOP RECURRING blocks (occurrences desc) — the ones worth fixing first
  - recent events (tail of blocks.jsonl)
  - promotion-ready (occurrences >= threshold, structural class) — the P2 candidates

This is the monitoring the single-spoke bake (P6) verifies: a recurring block here
is a signal to fix the underlying AP friction, then watch occurrences stop growing.

Usage:
  python3 capgraph_monitor.py --root <spoke-root> [--tail 10] [--promote-threshold 3] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capgraph_blocks as cb  # noqa: E402

STRUCTURAL = {"precondition_unmet", "qc_error", "execute_when"}


def _load(root):
    local = cb._find_spoke_local(root)
    if local is None:
        return None, [], []
    graph = cb._load_graph(local / cb.LOCAL_GRAPH)
    aps = [e for e in graph.get("entries", []) if e.get("kind") == "antipattern"]
    events = []
    log = local / cb.BLOCKS_LOG
    if log.exists():
        for line in log.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return local, aps, events


def build_report(root, tail=10, promote_threshold=3):
    local, aps, events = _load(root)
    aps_sorted = sorted(aps, key=lambda e: e.get("occurrences", 0), reverse=True)
    promo = [e for e in aps if e.get("occurrences", 0) >= promote_threshold
             and e.get("block_class") in STRUCTURAL and e.get("status") == "open"
             and not e.get("promoted_at")]
    return {
        "spoke_local": str(local) if local else None,
        "summary": cb.summarize(root),
        "top_recurring": [
            {"id": e["id"], "block_class": e.get("block_class"),
             "occurrences": e.get("occurrences"), "status": e.get("status"),
             "resolution": e.get("resolution"), "last_seen": e.get("last_seen")}
            for e in aps_sorted[:10]
        ],
        "promotion_ready": [e["id"] for e in promo],
        "recent_events": events[-tail:],
    }


def render(rep):
    s = rep["summary"]
    out = []
    out.append("┏━━ CapabilitiesGraph block-memory (AP antipatterns) ━━")
    out.append(f"┃ store: {rep['spoke_local']}")
    out.append(f"┃ antipatterns={s['total_antipatterns']}  occurrences={s['total_occurrences']}  "
               f"open={s['open']}  resolved={s['resolved']}")
    out.append(f"┃ by_class: {s['by_class'] or '{}'}")
    out.append("┣━━ TOP RECURRING (fix these first) ━━")
    if rep["top_recurring"]:
        for e in rep["top_recurring"]:
            res = e["resolution"] or "—"
            out.append(f"┃  {e['occurrences']:>3}×  [{e['block_class']:<16}] {e['id']}  "
                       f"status={e['status']} resolution={res}")
    else:
        out.append("┃  (none yet)")
    out.append("┣━━ PROMOTION-READY (P2: structural + recurring) ━━")
    out.append(f"┃  {rep['promotion_ready'] or '(none)'}")
    out.append("┣━━ RECENT EVENTS ━━")
    for ev in rep["recent_events"]:
        out.append(f"┃  {ev.get('ts','?')[:19]}  {ev.get('block_class','?'):<16} {ev.get('lug_id','?')}")
    out.append("┗━━")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="capgraph_monitor — AP block-memory dashboard")
    ap.add_argument("--root", help="spoke root or spoke/local path")
    ap.add_argument("--tail", type=int, default=10)
    ap.add_argument("--promote-threshold", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rep = build_report(args.root, args.tail, args.promote_threshold)
    print(json.dumps(rep, indent=2) if args.json else render(rep))


if __name__ == "__main__":
    main()
