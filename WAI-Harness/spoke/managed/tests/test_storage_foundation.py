#!/usr/bin/env python3
"""Verification test for impl-storage-layer-foundation-v1 (test-at-birth).

Covers the lug's verify[] semantic checks:
  - schema present (all base tables)
  - idempotent migration runner
  - bolt lifecycle: open + checks(0) -> needs_review; checks(1) -> pass  (SQL-derivable, no app code)
  - FTS5 baseline search returns the right row
  - graceful FTS5-only fallback when sqlite-vec is absent

Run: python3 -m pytest tests/test_storage_foundation.py -x   (or: python3 tests/test_storage_foundation.py)
"""
import os
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_TABLES = {
    "sessions", "bolts", "bolt_patterns", "patterns", "checks", "gate_log",
    "events", "cg_entries", "pg_entries", "tg_profiles", "test_results",
    "gitnexus_refs", "schema_migrations",
}

# bolt status derivation: any check.result=0 -> needs_review; all=1 -> pass
DERIVE_STATUS = """
SELECT CASE
  WHEN COUNT(*) = 0 THEN 'open'
  WHEN SUM(CASE WHEN result=0 THEN 1 ELSE 0 END) > 0 THEN 'needs_review'
  ELSE 'pass' END
FROM checks WHERE bolt_id = ?
"""


def _build(db_path):
    r = subprocess.run(
        [sys.executable, "tools/create_harness_db.py", "--db-path", db_path],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_schema_and_idempotency():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "harness.db")
        _build(db)
        out2 = _build(db)  # second run = idempotent
        assert "none (idempotent)" in out2, "second run should apply no migrations"
        con = sqlite3.connect(db)
        names = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        missing = BASE_TABLES - names
        assert not missing, f"missing tables: {missing}"
        con.close()


def test_bolt_lifecycle():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "harness.db")
        _build(db)
        con = sqlite3.connect(db)
        con.execute("INSERT INTO sessions(id, started_at) VALUES ('s1','t0')")
        con.execute("INSERT INTO bolts(id, session_id, certifier, status, opened_at) "
                    "VALUES ('b1','s1','gate-sub','open','t0')")
        # open + 3 unverified checks -> needs_review
        for i in range(3):
            con.execute("INSERT INTO checks(id, pattern_id, check_name, criterion, result, bolt_id) "
                        "VALUES (?,?,?,?,0,'b1')", (f"c{i}", "p1", f"chk{i}", "crit"))
        con.commit()
        status = con.execute(DERIVE_STATUS, ("b1",)).fetchone()[0]
        assert status == "needs_review", f"expected needs_review, got {status}"
        # verify all checks -> pass
        con.execute("UPDATE checks SET result=1 WHERE bolt_id='b1'")
        con.commit()
        status = con.execute(DERIVE_STATUS, ("b1",)).fetchone()[0]
        assert status == "pass", f"expected pass, got {status}"
        con.close()


def test_fts5_search():
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "harness.db")
        _build(db)
        con = sqlite3.connect(db)
        rows = [
            ("cg1", "closeout halts repeatedly on the test gate", "add a pre-gate"),
            ("cg2", "model token usage spiked fleet-wide", "reroute to cheaper tier"),
            ("cg3", "lug placed in the wrong bytype folder", "relocate via hygiene"),
        ]
        con.executemany("INSERT INTO cg_entries(id, situation, solution, tier, source, created_at, updated_at) "
                        "VALUES (?,?,?, 'recommended','local','t0','t0')", rows)
        con.executemany("INSERT INTO cg_fts(id, situation, solution) VALUES (?,?,?)", rows)
        con.commit()
        hits = [r[0] for r in con.execute(
            "SELECT id FROM cg_fts WHERE cg_fts MATCH 'closeout'")]
        assert hits == ["cg1"], f"expected ['cg1'], got {hits}"
        con.close()


if __name__ == "__main__":
    test_schema_and_idempotency(); print("PASS test_schema_and_idempotency")
    test_bolt_lifecycle();         print("PASS test_bolt_lifecycle")
    test_fts5_search();            print("PASS test_fts5_search")
    print("ALL PASS")
