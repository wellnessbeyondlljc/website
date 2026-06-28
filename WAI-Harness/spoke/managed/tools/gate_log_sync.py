#!/usr/bin/env python3
"""gate_log_sync.py — JSONL↔SQLite mirror + ownership routing for gate events.

(impl-gate-storage-topology-v1) The gate-log.jsonl files are the append-only
source of truth (survive without the DB, readable by any tool). This tool tails
them and upserts new rows into the SQLite `gate_log` table — the query/analysis
mirror — idempotently (INSERT OR IGNORE on the event id PK), so re-running never
duplicates and a crash mid-sync just re-runs.

It also routes a gate event to the OWNING advisor's patterns/ folder per the
flow definition's `owner` (ozi/historian/expediter → advisors/<owner>/patterns/;
main-agent → top-level WAI-Spoke/patterns/) — the advisor that calls the gate
owns its events.

API:
  sync(db_path=..., jsonl_path=...) -> indexed_count
  route_event(event, patterns_root=..., advisors_root=..., flow_defs_dir=...) -> path
"""
import argparse
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wai_paths import resolve_wai_root  # noqa: E402  (v3/v4 resolver)


def _spoke_base():
    """Resolve the live spoke working-base (v4: WAI-Harness/spoke/local; v3:
    WAI-Spoke), independent of nesting depth. PRE-FIX the DEFAULT_* constants
    hardcoded a relative 'WAI-Spoke/...' tree -> on a v4 spoke the sync read an
    empty/absent gate-log and routed events into a dead tree (impl-fix-p2-v3noop-sweep-v1)."""
    start = Path(__file__).resolve()
    for anc in start.parents:
        if (anc / "WAI-Harness" / "spoke" / "local").is_dir():
            base, mode = resolve_wai_root(str(anc))
            if base and mode != "none":
                return Path(base)
    for anc in start.parents:
        if (anc / "WAI-Spoke").is_dir():
            return anc / "WAI-Spoke"
    return start.parent.parent / "WAI-Spoke"


_SPOKE_BASE = _spoke_base()
DEFAULT_DB = str(_SPOKE_BASE / "managed/harness.db")
DEFAULT_JSONL = str(_SPOKE_BASE / "patterns/gate-log.jsonl")
DEFAULT_PATTERNS_ROOT = str(_SPOKE_BASE / "patterns")
DEFAULT_ADVISORS_ROOT = str(_SPOKE_BASE / "advisors")
DEFAULT_FLOW_DEFS = str(_SPOKE_BASE / "patterns/flow-definitions")

GATE_COLS = ("id", "flow_id", "step_id", "session_id", "attempt",
             "disposition", "evidence", "refinement", "created_at")
ADVISOR_OWNERS = ("ozi", "historian", "expediter")


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _row(e):
    r = dict(e)
    r.setdefault("id", e.get("event_id"))
    vals = []
    for c in GATE_COLS:
        v = r.get(c)
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        vals.append(v)
    return vals


def sync(db_path=DEFAULT_DB, jsonl_path=DEFAULT_JSONL):
    """Upsert gate-log.jsonl rows into the gate_log table. Idempotent by id."""
    rows = _read_jsonl(jsonl_path)
    if not rows:
        return 0
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    before = con.execute("SELECT COUNT(*) FROM gate_log").fetchone()[0]
    for e in rows:
        con.execute(
            f"INSERT OR IGNORE INTO gate_log ({','.join(GATE_COLS)}) "
            f"VALUES ({','.join('?' * len(GATE_COLS))})", _row(e))
    con.commit()
    after = con.execute("SELECT COUNT(*) FROM gate_log").fetchone()[0]
    con.close()
    return after - before


def _flow_owner(flow_id, flow_defs_dir):
    for p in glob.glob(os.path.join(flow_defs_dir, "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if d.get("flow_id") == flow_id:
            return d.get("owner", "main-agent")
    return "main-agent"


def route_event(event, patterns_root=DEFAULT_PATTERNS_ROOT,
                advisors_root=DEFAULT_ADVISORS_ROOT, flow_defs_dir=DEFAULT_FLOW_DEFS):
    """Append a gate event to the OWNING advisor's patterns/gate-log.jsonl
    (per the flow definition's owner). Returns the file path it landed in."""
    owner = _flow_owner(event.get("flow_id"), flow_defs_dir)
    if owner in ADVISOR_OWNERS:
        d = os.path.join(advisors_root, owner, "patterns")
    else:  # main-agent (or unknown) -> top-level patterns/
        d = patterns_root
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "gate-log.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="sync gate-log.jsonl into the gate_log table")
    ap.add_argument("--db-path", default=DEFAULT_DB)
    ap.add_argument("--jsonl-path", default=DEFAULT_JSONL)
    a = ap.parse_args(argv)
    n = sync(a.db_path, a.jsonl_path)
    print(f"[gate_log_sync] indexed {n} new gate event(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
