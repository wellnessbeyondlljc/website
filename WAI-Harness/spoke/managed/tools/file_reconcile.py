#!/usr/bin/env python3
"""file_reconcile.py — closeout file-update reconciliation notices (epic AC21, Stream L).

When a session's closeout commits a file, emit a file-update notice (typed event) to
every OTHER live session that holds/owns that file, so the owning session reconciles
WITH awareness (sees what changed, by whom, when) instead of being silently overwritten.
Builds on the file-ownership map (manifest) + concurrent-session-identity. The closeout
becomes a publisher of file-change events, not a silent committer.
"""
import argparse
import json
import os
import sys

import db_writer  # reuse the durable event journal (single-writer floor)


def emit_notices(committed_file, committing_session, live_sessions, ownership,
                 commit_sha=None, ts=None, journal_path=db_writer.DEFAULT_JOURNAL):
    """Emit a file_update_notice event to each live owner of committed_file (except the committer)."""
    owner = ownership.get(committed_file)
    notified = []
    for sid in live_sessions:
        if sid == committing_session:
            continue
        if owner == sid:  # this live session owns/holds the committed file
            db_writer.enqueue_event({
                "ts": ts or "",
                "session": sid,
                "actor": "file_reconcile",
                "type": "file_update_notice",
                "subject_ref": committed_file,
                "status": "needs_reconcile",
                "evidence": {"committed_by": committing_session, "commit": commit_sha,
                             "file": committed_file, "reconcile": "review diff before next write"},
            }, journal_path=journal_path)
            notified.append(sid)
    return notified


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--committing-session", required=True)
    ap.add_argument("--live-sessions", required=True, help="comma-separated")
    ap.add_argument("--ownership", required=True, help="JSON {file: owner_session}")
    ap.add_argument("--commit", default=None)
    ap.add_argument("--journal-path", default=db_writer.DEFAULT_JOURNAL)
    args = ap.parse_args(argv)
    n = emit_notices(args.file, args.committing_session, args.live_sessions.split(","),
                     json.loads(args.ownership), args.commit, journal_path=args.journal_path)
    print(f"[reconcile] notices emitted to: {n or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
