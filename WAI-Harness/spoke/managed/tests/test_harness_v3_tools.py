"""Tests for the Harness v3 Stream B tools: base_cut_draft + teaching_reconcile."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import base_cut_draft as bcd  # noqa: E402
import teaching_reconcile as tr  # noqa: E402


# --- base_cut_draft -------------------------------------------------------

def test_base_cut_below_cap_is_noop(tmp_path):
    pdir = tmp_path / "patches"; pdir.mkdir()
    (pdir / "index.json").write_text(json.dumps([{"id": "patch-001"}]))
    assert bcd.check(pdir, cap=10)["at_cap"] is False
    out = bcd.draft(pdir, tmp_path / "base", "3.1.0", tmp_path / "lugs", cap=10)
    assert out["action"] == "noop"


def test_base_cut_at_cap_drafts(tmp_path):
    pdir = tmp_path / "patches"; pdir.mkdir()
    entries = [{"id": f"patch-{i:03d}", "file": f"p{i}.md", "base_version": "3.0.0"} for i in range(10)]
    (pdir / "index.json").write_text(json.dumps(entries))
    assert bcd.check(pdir, cap=10)["at_cap"] is True
    out = bcd.draft(pdir, tmp_path / "base", "3.1.0", tmp_path / "lugs", cap=10)
    assert out["action"] == "drafted"
    assert Path(out["report"]).exists()
    lug = json.loads(Path(out["approval_lug"]).read_text())
    assert lug["type"] == "task" and lug["status"] == "open"
    assert "APPROVE base cut" in lug["title"]
    # Active base is NOT mutated — only a candidate dir is created.
    assert "candidate" in out["candidate_dir"]


# --- teaching_reconcile ---------------------------------------------------

def test_reconcile_four_verdicts(tmp_path):
    idx = tmp_path / "index.json"
    idx.write_text(json.dumps([
        {"id": "signal-20260331-0535-from-minder", "title": ""},
        {"id": "skill-wai-lug-advisor-v2", "title": "Lug advisor"},
        {"id": "skill-wai-lug-advisor-v3", "title": "Lug advisor v3"},
        {"id": "wai-step-0-5-priority-gate-v1", "title": "Priority gate"},
        {"id": "wai-pattern-bolt-model-v1", "title": "Pattern/bolt model"},
    ]))
    out = tr.plan(idx, absorbed_hints={"wai-step-0-5-priority-gate-v1"}, cap=10)
    assert out["counts"] == {"KEEP": 2, "ABSORBED": 1, "STALE": 1, "DUPLICATE": 1}
    assert out["keep_within_cap"] is True
    ids = {r["id"]: r["verdict"] for b in out["buckets"].values() for r in b}
    assert ids["signal-20260331-0535-from-minder"] == "STALE"
    assert ids["skill-wai-lug-advisor-v2"] == "DUPLICATE"
    assert ids["skill-wai-lug-advisor-v3"] == "KEEP"
    assert ids["wai-step-0-5-priority-gate-v1"] == "ABSORBED"


def test_reconcile_cap_overflow_flagged(tmp_path):
    idx = tmp_path / "index.json"
    idx.write_text(json.dumps([{"id": f"keep-{i}-v1", "title": f"k{i}"} for i in range(12)]))
    out = tr.plan(idx, cap=10)
    assert out["counts"]["KEEP"] == 12
    assert out["keep_within_cap"] is False
    assert out["over_by"] == 2
