#!/usr/bin/env python3
"""Test-at-birth for CG -> harness.db materialization (tools/materialize_cg.py, AC16 SQLite half).

Spins a temp harness.db via the existing create_harness_db.py (phase-0), materializes
synthetic resolved CG entries, and verifies the rows + FTS index + idempotency. Does not
touch the real WAI-Spoke/managed/harness.db.
"""
import importlib.util
import json
import os
import sqlite3
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(
        mod, os.path.join(ROOT, "tools", f"{mod}.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


M = _load("materialize_cg")
CREATE = _load("create_harness_db")


def _fresh_db(d):
    db = os.path.join(d, "harness.db")
    CREATE.main(["--db-path", db, "--migrations-dir", os.path.join(ROOT, "managed", "migrations")])
    return db


def _entries():
    return [
        {"id": "cap-a", "situation": "closeout must reconcile and commit",
         "solution": "run /wai-closeout", "tier": "mandated", "owner_advisor": "ozi",
         "file_paths": ["templates/commands/wai-closeout.md"], "symbol_refs": [],
         "source": "hub"},
        {"id": "cap-b", "situation": "every turn must leave a track entry",
         "solution": "write track-buffer.json", "tier": "mandated", "owner_advisor": "historian",
         "file_paths": ["templates/commands/wai-track.md"], "symbol_refs": [], "source": "hub"},
        {"id": "cap-c", "situation": "periodic cross-tool audit surfaces drift",
         "solution": "run tool advisor", "tier": "recommended", "owner_advisor": "ozi",
         "file_paths": [], "symbol_refs": [], "source": "hub"},
    ]


def test_materialize_inserts_rows():
    with tempfile.TemporaryDirectory() as d:
        db = _fresh_db(d)
        n = M.materialize_cg(db, _entries())
        assert n == 3
        con = sqlite3.connect(db)
        assert con.execute("SELECT COUNT(*) FROM cg_entries").fetchone()[0] == 3
        # file_paths round-trips as JSON
        fp = con.execute("SELECT file_paths FROM cg_entries WHERE id='cap-a'").fetchone()[0]
        assert json.loads(fp) == ["templates/commands/wai-closeout.md"]
        con.close()


def test_fts_search():
    with tempfile.TemporaryDirectory() as d:
        db = _fresh_db(d)
        M.materialize_cg(db, _entries())
        hits = M.search_cg(db, "closeout")
        assert "cap-a" in hits
        hits2 = M.search_cg(db, "track")
        assert "cap-b" in hits2


def test_idempotent_rematerialize():
    with tempfile.TemporaryDirectory() as d:
        db = _fresh_db(d)
        M.materialize_cg(db, _entries())
        M.materialize_cg(db, _entries())  # re-run
        con = sqlite3.connect(db)
        assert con.execute("SELECT COUNT(*) FROM cg_entries").fetchone()[0] == 3, "no dupes on re-run"
        # cg_fts stays consistent (no orphan rows)
        assert con.execute("SELECT COUNT(*) FROM cg_fts").fetchone()[0] == 3
        con.close()


def test_update_on_rematerialize():
    with tempfile.TemporaryDirectory() as d:
        db = _fresh_db(d)
        M.materialize_cg(db, _entries())
        changed = _entries()
        changed[0]["solution"] = "run /wai-closeout (updated)"
        M.materialize_cg(db, changed)
        con = sqlite3.connect(db)
        sol = con.execute("SELECT solution FROM cg_entries WHERE id='cap-a'").fetchone()[0]
        assert sol == "run /wai-closeout (updated)"
        con.close()


def test_tier_preserved():
    with tempfile.TemporaryDirectory() as d:
        db = _fresh_db(d)
        M.materialize_cg(db, _entries())
        con = sqlite3.connect(db)
        tiers = dict(con.execute("SELECT id, tier FROM cg_entries").fetchall())
        assert tiers["cap-a"] == "mandated"
        assert tiers["cap-c"] == "recommended"
        con.close()
