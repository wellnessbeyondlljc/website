#!/usr/bin/env python3
"""create_harness_db.py — WAI-Harness v4 storage layer foundation (spec-storage-layer-v1).

Idempotent, migration-versioned creation of harness.db:
  - applies any unapplied .sql migration in managed/migrations/ in version order
  - records applied versions in schema_migrations (safe to run twice)
  - FTS5 baseline always; vector tables (sqlite-vec) only if the extension loads,
    otherwise logs that vector search is disabled and FTS5 is the active path
  - sets WAL + busy_timeout (forward-compatible with the single-writer write path)

Usage:
  python3 tools/create_harness_db.py [--db-path PATH] [--migrations-dir DIR]
Defaults: --db-path WAI-Spoke/managed/harness.db  --migrations-dir managed/migrations
"""
import argparse
import datetime
import os
import sqlite3
import sys

VECTOR_DIM = 384  # bge-small/MiniLM class (spec-storage-layer-v1)
VECTOR_TABLES = ("cg_embeddings", "session_embeddings", "pattern_embeddings")


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _applied_versions(con):
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    return {r[0] for r in con.execute("SELECT version FROM schema_migrations")}


def _apply_migrations(con, migrations_dir):
    applied = _applied_versions(con)
    files = sorted(f for f in os.listdir(migrations_dir) if f.endswith(".sql"))
    ran = []
    for fn in files:
        version = fn.split("_", 1)[0]  # "001" from "001_initial.sql"
        if version in applied:
            continue
        sql = open(os.path.join(migrations_dir, fn), encoding="utf-8").read()
        con.executescript(sql)
        con.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?,?)",
            (version, _utcnow()),
        )
        con.commit()
        ran.append(fn)
    return ran, files


def _try_vector_tables(con):
    """Create vec0 tables only if sqlite-vec loads. Returns True if vector search is enabled."""
    try:
        con.enable_load_extension(True)
        con.load_extension("vec0")
    except Exception as e:
        print(f"[storage] sqlite-vec unavailable ({str(e)[:50]}...) "
              f"-> vector search DISABLED, FTS5 is the active search path")
        return False
    for t in VECTOR_TABLES:
        con.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {t} USING vec0(embedding float[{VECTOR_DIM}])"
        )
    con.commit()
    print(f"[storage] sqlite-vec loaded -> vector tables created ({VECTOR_DIM}-dim)")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default="WAI-Spoke/managed/harness.db")
    ap.add_argument("--migrations-dir", default="managed/migrations")
    args = ap.parse_args(argv)

    os.makedirs(os.path.dirname(os.path.abspath(args.db_path)), exist_ok=True)
    existed = os.path.exists(args.db_path)

    con = sqlite3.connect(args.db_path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")

    ran, all_files = _apply_migrations(con, args.migrations_dir)
    vector_enabled = _try_vector_tables(con)

    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name")]
    con.close()

    print(f"[storage] db {'updated' if existed else 'created'}: {args.db_path}")
    print(f"[storage] migrations applied this run: {ran or 'none (idempotent)'}")
    print(f"[storage] migrations on disk: {all_files}")
    print(f"[storage] tables: {len(tables)} -> {', '.join(tables)}")
    print(f"[storage] vector_search: {'enabled' if vector_enabled else 'FTS5-only fallback'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
