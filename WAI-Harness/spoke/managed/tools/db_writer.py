#!/usr/bin/env python3
"""db_writer.py — single-writer queue for harness.db (spec-storage-layer-v1 write_concurrency).

The JSONL event journal is the durable floor; harness.db is the indexed query view.
Advisors call enqueue_event() ONLY (append to journal, non-blocking, crash-safe).
A single writer worker drains the journal into SQLite sequentially + idempotently
(INSERT OR IGNORE on event_id PK) — so concurrent advisors never contend on the DB
and a busy/locked DB or a crash mid-drain never loses an event (replay from journal).

API:
  enqueue_event(event: dict, journal_path=...) -> event_id   # append-only, non-blocking
  drain(db_path=..., journal_path=...) -> indexed_count        # the single writer
"""
import argparse
import json
import os
import sqlite3
import sys
import uuid

DEFAULT_DB = "WAI-Spoke/managed/harness.db"
DEFAULT_JOURNAL = "WAI-Spoke/managed/events-journal.jsonl"
EVENT_COLS = ("event_id", "ts", "spoke", "session", "actor", "type",
              "subject_ref", "status", "evidence", "correlation_id", "parent_event")


def enqueue_event(event, journal_path=DEFAULT_JOURNAL):
    """Append a typed event to the durable journal. Non-blocking; O_APPEND is atomic per line."""
    event = dict(event)
    event.setdefault("event_id", uuid.uuid4().hex)
    os.makedirs(os.path.dirname(os.path.abspath(journal_path)), exist_ok=True)
    line = json.dumps(event, separators=(",", ":")) + "\n"
    # single append+flush — atomic for line-sized writes on POSIX
    with open(journal_path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())
    return event["event_id"]


def _connect(db_path):
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def drain(db_path=DEFAULT_DB, journal_path=DEFAULT_JOURNAL):
    """The SINGLE writer: index all journal events into SQLite, idempotently (INSERT OR IGNORE)."""
    if not os.path.exists(journal_path):
        return 0
    con = _connect(db_path)
    before = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    with open(journal_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            vals = [e.get(c) for c in EVENT_COLS]
            # evidence may be a dict -> store as JSON text
            if isinstance(vals[EVENT_COLS.index("evidence")], (dict, list)):
                vals[EVENT_COLS.index("evidence")] = json.dumps(vals[EVENT_COLS.index("evidence")])
            con.execute(
                f"INSERT OR IGNORE INTO events ({','.join(EVENT_COLS)}) "
                f"VALUES ({','.join('?' * len(EVENT_COLS))})", vals)
    con.commit()
    after = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    con.close()
    return after - before


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default=DEFAULT_DB)
    ap.add_argument("--journal-path", default=DEFAULT_JOURNAL)
    args = ap.parse_args(argv)
    n = drain(args.db_path, args.journal_path)
    print(f"[db_writer] drained {n} new event(s) into {args.db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
