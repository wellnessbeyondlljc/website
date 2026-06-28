#!/usr/bin/env python3
"""retention.py — two-tier event retention (spec-storage-layer-v1 retention_policy).

Raw/trace events older than the window are AGGREGATED into event_daily_summary
(preserving the trend signal) and then PRUNED. Durable entities are never pruned.
Pruning is itself a logged event (type=retention), never silent.

Usage: python3 tools/retention.py [--db-path PATH] [--window-days 14] [--now ISO]
(--now is injected for deterministic testing; defaults to current UTC.)
"""
import argparse
import datetime
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _managed_base(spoke_root="."):
    """The dir holding harness.db, base-aware. On a v4 spoke this resolves to
    WAI-Harness/spoke/local/managed; PRE-FIX the hardcoded WAI-Spoke default silently
    read a nonexistent tree (impl-fix-p2-v3noop-sweep-v1). Mirrors db_writer._managed_base."""
    try:
        from wai_paths import resolve_wai_root
        root, mode = resolve_wai_root(str(spoke_root))
        if root and mode != "none":
            return Path(root) / "managed"
    except Exception:
        pass
    return Path(spoke_root) / "WAI-Spoke" / "managed"  # last-resort v3 fallback


DEFAULT_DB = str(_managed_base() / "harness.db")
# raw/trace event types that get aggregated + pruned past the window
RAW_TYPES = ("gate", "test", "workflow_step", "provider_usage", "dispatch_audit")
# durable types are never pruned (lug_state, bolt, decision, verdict, session, migration,
# attention, evolution_proposal, hygiene_action, retention)


def _utcnow_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run(db_path=DEFAULT_DB, window_days=14, now_iso=None):
    now_iso = now_iso or _utcnow_iso()
    now = datetime.datetime.fromisoformat(now_iso)
    cutoff = (now - datetime.timedelta(days=window_days)).isoformat()

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    placeholders = ",".join("?" * len(RAW_TYPES))

    # aggregate raw events older than cutoff into daily summaries
    rows = con.execute(
        f"SELECT substr(ts,1,10) AS day, type, COUNT(*) "
        f"FROM events WHERE type IN ({placeholders}) AND ts < ? "
        f"GROUP BY day, type", (*RAW_TYPES, cutoff)).fetchall()
    for day, typ, cnt in rows:
        con.execute(
            "INSERT INTO event_daily_summary(day, type, count, aggregated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(day, type) DO UPDATE SET count = count + excluded.count, "
            "aggregated_at = excluded.aggregated_at",
            (day, typ, cnt, now_iso))

    # prune the aggregated raw rows
    cur = con.execute(
        f"DELETE FROM events WHERE type IN ({placeholders}) AND ts < ?", (*RAW_TYPES, cutoff))
    pruned = cur.rowcount

    # log the retention action as a durable event (not silent)
    con.execute(
        "INSERT OR IGNORE INTO events(event_id, ts, actor, type, status, evidence) "
        "VALUES (?,?,?,?,?,?)",
        (f"retention-{now.strftime('%Y%m%dT%H%M%S')}", now_iso, "retention", "retention",
         "completed", f"aggregated {len(rows)} day/type groups, pruned {pruned} raw rows older than {cutoff}"))
    con.commit()
    con.close()
    return {"aggregated_groups": len(rows), "pruned": pruned, "cutoff": cutoff}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default=DEFAULT_DB)
    ap.add_argument("--window-days", type=int, default=14)
    ap.add_argument("--now", default=None)
    args = ap.parse_args(argv)
    res = run(args.db_path, args.window_days, args.now)
    print(f"[retention] {res}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
