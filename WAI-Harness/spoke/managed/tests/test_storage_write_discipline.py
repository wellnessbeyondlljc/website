#!/usr/bin/env python3
"""Verification test for impl-storage-write-discipline-v1 (test-at-birth).

Covers verify[]: WAL/busy_timeout, single-writer queue under concurrency, durable
journal floor (idempotent replay), two-tier retention, workflow_state_telemetry table.
"""
import importlib.util
import os
import sqlite3
import subprocess
import sys
import threading
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _build(db):
    r = subprocess.run([sys.executable, "tools/create_harness_db.py", "--db-path", db],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_wal_and_workflow_table():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "h.db"); _build(db)
        con = sqlite3.connect(db)
        assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "workflow_state_telemetry" in names and "event_daily_summary" in names
        con.close()


def test_single_writer_concurrency_and_replay():
    dw = _load("db_writer")
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "h.db"); jr = os.path.join(d, "j.jsonl"); _build(db)
        # 50 concurrent enqueues (advisors are non-blocking; journal is the queue)
        def emit(i):
            dw.enqueue_event({"event_id": f"e{i}", "ts": "2026-06-09T00:00:00", "type": "gate",
                              "actor": "t", "status": "approved"}, journal_path=jr)
        threads = [threading.Thread(target=emit, args=(i,)) for i in range(50)]
        [t.start() for t in threads]; [t.join() for t in threads]
        assert sum(1 for _ in open(jr)) == 50, "all 50 enqueues land in the journal"
        n = dw.drain(db, jr)
        assert n == 50, f"single writer indexed all 50, got {n}"
        # idempotent re-drain (simulates crash/replay): no duplicates
        n2 = dw.drain(db, jr)
        assert n2 == 0, f"re-drain idempotent, got {n2}"
        con = sqlite3.connect(db)
        assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 50
        con.close()


def test_retention_aggregates_and_preserves_durable():
    dw = _load("db_writer"); ret = _load("retention")
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "h.db"); jr = os.path.join(d, "j.jsonl"); _build(db)
        # old raw event (should aggregate+prune) + old durable event (should survive)
        dw.enqueue_event({"event_id": "old-raw", "ts": "2026-01-01T00:00:00", "type": "gate", "actor": "t"}, jr)
        dw.enqueue_event({"event_id": "old-decision", "ts": "2026-01-01T00:00:00", "type": "decision", "actor": "t"}, jr)
        dw.enqueue_event({"event_id": "new-raw", "ts": "2026-06-09T00:00:00", "type": "gate", "actor": "t"}, jr)
        dw.drain(db, jr)
        res = ret.run(db, window_days=14, now_iso="2026-06-09T12:00:00")
        assert res["pruned"] == 1, f"only the 1 old raw event pruned, got {res['pruned']}"
        con = sqlite3.connect(db)
        ids = {r[0] for r in con.execute("SELECT event_id FROM events")}
        assert "old-raw" not in ids, "old raw event pruned"
        assert "old-decision" in ids, "durable event preserved"
        assert "new-raw" in ids, "in-window raw event preserved"
        # aggregate captured the pruned signal + retention logged
        assert con.execute("SELECT count FROM event_daily_summary WHERE type='gate'").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM events WHERE type='retention'").fetchone()[0] == 1
        con.close()


if __name__ == "__main__":
    test_wal_and_workflow_table();                 print("PASS test_wal_and_workflow_table")
    test_single_writer_concurrency_and_replay();   print("PASS test_single_writer_concurrency_and_replay")
    test_retention_aggregates_and_preserves_durable(); print("PASS test_retention_aggregates_and_preserves_durable")
    print("ALL PASS")
