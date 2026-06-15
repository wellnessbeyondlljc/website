#!/usr/bin/env python3
"""explain_chain.py — reconstruct one causal chain from the event bus.

Given a correlation_id, return the ordered cause→effect chain of events
(goal → queue → dispatch → gate → bolt …), with each step's decision parent
resolved. This is the "explain why the last N events happened" surface — the
single biggest gap the v4 audit found.

Reads the durable journal floor (db_writer's events-journal.jsonl) so it works
even before/without the indexed DB. Ordering is by the parent_event DAG
(topological); ties and orphan roots fall back to ts order.

API:
  chain(correlation_id, journal_path=...) -> [event, ...]  # causal order, parents resolved
  format_chain(events) -> str                              # human-readable trace
"""
import argparse
import json
import os
import sys

import db_writer

DEFAULT_JOURNAL = db_writer.DEFAULT_JOURNAL


def _read_journal(journal_path):
    if not os.path.exists(journal_path):
        return []
    out = []
    with open(journal_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def chain(correlation_id, journal_path=DEFAULT_JOURNAL):
    """Return the events for one correlation_id in causal (cause→effect) order.

    A decision parent that lives outside the correlation set is pulled in and
    placed before its child so the 'why' is always visible in the trace."""
    all_events = _read_journal(journal_path)
    by_id = {e["event_id"]: e for e in all_events if e.get("event_id")}

    members = {e["event_id"]: e for e in all_events
               if e.get("correlation_id") == correlation_id and e.get("event_id")}
    # pull in decision parents referenced from inside the chain even if they
    # carry a different/empty correlation_id — the cause must be visible.
    for e in list(members.values()):
        p = e.get("parent_event")
        if p and p not in members and p in by_id:
            members[p] = by_id[p]

    # topological order by parent_event; fall back to ts for roots/ties.
    ordered, visited = [], set()

    def visit(eid):
        if eid in visited or eid not in members:
            return
        visited.add(eid)
        parent = members[eid].get("parent_event")
        if parent in members:
            visit(parent)
        ordered.append(members[eid])

    for eid in sorted(members, key=lambda i: members[i].get("ts", "")):
        visit(eid)
    return ordered


def format_chain(events):
    lines = []
    for i, e in enumerate(events):
        marker = "└─" if i == len(events) - 1 else "├─"
        why = ""
        if e.get("type") == "decision":
            ev = e.get("evidence")
            if isinstance(ev, str):
                try:
                    ev = json.loads(ev)
                except (ValueError, TypeError):
                    ev = {}
            if isinstance(ev, dict) and ev.get("rationale"):
                why = f"  (why: {ev['rationale']})"
        lines.append(f"{marker} [{e.get('ts','')}] {e.get('type','?')} "
                     f"· {e.get('actor','?')} · {e.get('status','?')} "
                     f"· {e.get('subject_ref','') or ''}{why}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="explain one causal chain by correlation_id")
    ap.add_argument("correlation_id")
    ap.add_argument("--journal-path", default=DEFAULT_JOURNAL)
    ap.add_argument("--json", action="store_true", help="emit the ordered events as JSON")
    a = ap.parse_args(argv)
    evs = chain(a.correlation_id, a.journal_path)
    if not evs:
        print(f"[explain_chain] no events for correlation_id {a.correlation_id}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(evs, indent=2))
    else:
        print(f"chain {a.correlation_id} ({len(evs)} events):")
        print(format_chain(evs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
