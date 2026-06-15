"""Acceptance proof: file_reconcile.emit_notices — closeout file-update reconciliation (AC21).
A committed file notifies OTHER live owners (not the committer), durably, so no silent overwrite.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import file_reconcile as fr  # noqa: E402


def _read(journal):
    p = Path(journal)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def test_notifies_other_owner_not_committer(tmp_path):
    journal = tmp_path / "events.jsonl"
    notified = fr.emit_notices(
        committed_file="tools/x.py", committing_session="sessA",
        live_sessions=["sessA", "sessB"], ownership={"tools/x.py": "sessB"},
        commit_sha="abc123", ts="2026-06-10T08:00:00Z", journal_path=str(journal))
    assert notified == ["sessB"]
    evs = _read(journal)
    assert len(evs) == 1
    e = evs[0]
    assert e["type"] == "file_update_notice" and e["session"] == "sessB"
    assert e["status"] == "needs_reconcile" and e["evidence"]["committed_by"] == "sessA"


def test_no_notice_when_committer_is_sole_owner(tmp_path):
    journal = tmp_path / "events.jsonl"
    notified = fr.emit_notices(
        committed_file="tools/y.py", committing_session="sessA",
        live_sessions=["sessA"], ownership={"tools/y.py": "sessA"},
        journal_path=str(journal))
    assert notified == [] and _read(journal) == []


def test_unowned_file_emits_no_notice(tmp_path):
    journal = tmp_path / "events.jsonl"
    notified = fr.emit_notices(
        committed_file="tools/z.py", committing_session="sessA",
        live_sessions=["sessA", "sessB"], ownership={},  # nobody owns it
        journal_path=str(journal))
    assert notified == []
