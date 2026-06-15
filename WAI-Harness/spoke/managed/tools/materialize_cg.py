#!/usr/bin/env python3
"""Materialize the resolved CapabilitiesGraph into harness.db (spec-capabilitiesgraph-v1,
closes the AC16 SQLite half).

The resolver (resolve_capabilities_graph.py) produces capabilities-effective.json — the
JSON files are the durable source of truth. This indexes the resolved entries into the
SQLite cg_entries table + the cg_fts FTS5 index (spec-storage-layer-v1), so agents can
query the policy circle ('what solutions exist for this situation') instead of grepping.
The DB is a rebuildable index, never the source — a full re-materialization is idempotent.

Vector embeddings (cg_embeddings, sqlite-vec) are an optional enhancement; FTS5 is the
always-on baseline (spec-storage-layer-v1 search_baseline) so query never depends on a
network call or the extension being present.

This is a single-process BATCH sync (resolver output -> table), not concurrent advisor
telemetry, so it writes transactionally and directly (the db_writer single-writer queue
governs concurrent event writes, not deliberate batch materialization).

Pure core: materialize_cg(db_path, entries, now_iso) -> count.
"""
import argparse
import json
import os
import sqlite3
import sys

CG_COLS = ("id", "situation", "solution", "tier", "owner_advisor",
           "file_paths", "symbol_refs", "source", "created_at", "updated_at")


def materialize_cg(db_path, entries, now_iso=None):
    """Index resolved CG entries into cg_entries + rebuild cg_fts. Idempotent
    (INSERT OR REPLACE keyed on id; cg_fts fully rebuilt from cg_entries).
    Returns the number of entries materialized."""
    now = now_iso or __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat()
    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA busy_timeout=5000")
        rows = []
        for e in entries:
            rows.append((
                e.get("id"),
                e.get("situation", ""),
                e.get("solution", ""),
                e.get("tier", ""),
                e.get("owner_advisor"),
                json.dumps(e.get("file_paths", [])),
                json.dumps(e.get("symbol_refs", [])),
                e.get("source", ""),
                e.get("introduced_at") or e.get("created_at") or now,
                e.get("updated_at") or now,
            ))
        placeholders = ",".join("?" for _ in CG_COLS)
        con.executemany(
            f"INSERT OR REPLACE INTO cg_entries ({','.join(CG_COLS)}) VALUES ({placeholders})",
            rows,
        )
        # Rebuild the FTS index from the table so cg_fts stays consistent (regular FTS5).
        con.execute("DELETE FROM cg_fts")
        con.execute(
            "INSERT INTO cg_fts (id, situation, solution) "
            "SELECT id, situation, solution FROM cg_entries"
        )
        con.commit()
        return len(rows)
    finally:
        con.close()


def search_cg(db_path, query, limit=5):
    """FTS5 search over cg_entries.situation/solution (the always-on baseline)."""
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute(
            "SELECT id FROM cg_fts WHERE cg_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, limit),
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        con.close()


def _load_entries(effective_path):
    data = json.load(open(effective_path))
    if isinstance(data, list):
        return data
    return data.get("entries", [])


def main(argv):
    ap = argparse.ArgumentParser(description="Materialize the resolved CG into harness.db.")
    ap.add_argument("--db", default="WAI-Spoke/managed/harness.db")
    ap.add_argument("--effective",
                    default="/home/mario/projects/wheelwright/mywheel/WAI-Harness/"
                            "spoke/managed/runtime/capabilities-effective.json")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print(f"ERROR: harness.db not found at {args.db} — run tools/create_harness_db.py first",
              file=sys.stderr)
        return 2
    if not os.path.exists(args.effective):
        print(f"ERROR: resolved CG not found at {args.effective} — run "
              f"tools/resolve_capabilities_graph.py first", file=sys.stderr)
        return 2
    entries = _load_entries(args.effective)
    n = materialize_cg(args.db, entries)
    print(f"materialized {n} CG entries into {args.db} (cg_entries + cg_fts rebuilt)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
