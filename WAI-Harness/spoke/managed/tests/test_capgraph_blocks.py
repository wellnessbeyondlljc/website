#!/usr/bin/env python3
"""Tests for capgraph_blocks — the P0 keystone block-memory.

Covers AC1 (record dedup), AC2 (block_class correctness), AC3 (consult match +
miss), AC4 (never raises). Uses a tmp spoke/local so no real state is touched.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import capgraph_blocks as cb  # noqa: E402


@pytest.fixture
def local(tmp_path):
    p = tmp_path / "WAI-Harness" / "spoke" / "local"
    (p / "capabilitygraph").mkdir(parents=True)
    return str(tmp_path)  # pass the root; _find_spoke_local resolves spoke/local


def _graph(root):
    gp = Path(root) / "WAI-Harness" / "spoke" / "local" / "capabilities-graph-local.json"
    return json.loads(gp.read_text())


def test_record_dedup(local):  # AC1
    lug = {"id": "lug-a", "type": "impl"}
    sig1 = cb.record_block(lug, "execute_when", "all_completed: dep not done", spoke_local=local)
    sig2 = cb.record_block(lug, "execute_when", "all_completed: dep not done", spoke_local=local)
    assert sig1 == sig2
    aps = [e for e in _graph(local)["entries"] if e["kind"] == "antipattern"]
    assert len(aps) == 1
    assert aps[0]["occurrences"] == 2
    # append-only log got BOTH events
    log = (Path(local) / "WAI-Harness/spoke/local/capabilitygraph/blocks.jsonl").read_text().strip().splitlines()
    assert len(log) == 2


def test_seams_record_correct_class(local):  # AC2
    cb.record_block({"id": "l1", "type": "impl"}, "execute_when", "gate", spoke_local=local)
    cb.record_block({"id": "l2", "type": "impl"}, "stall", "2 failures", spoke_local=local)
    cb.record_block({"id": "l3", "type": "impl"}, "dispatch_failure", error_code="rc=1", spoke_local=local)
    cb.record_block({"id": "l4", "type": "impl"}, "precondition_unmet", "needs file", spoke_local=local)
    classes = {e["id"]: e["block_class"] for e in _graph(local)["entries"] if e["kind"] == "antipattern"}
    assert classes["ap-block:execute_when:l1"] == "execute_when"
    assert classes["ap-block:stall:l2"] == "stall"
    assert classes["ap-block:dispatch_failure:l3"] == "dispatch_failure"
    assert classes["ap-block:precondition_unmet:l4"] == "precondition_unmet"
    # invalid class is a no-op
    assert cb.record_block({"id": "x"}, "not_a_class", spoke_local=local) is None


def test_consult_match_and_miss(local):  # AC3
    blocked = {"id": "lug-blocked", "type": "impl"}
    cb.record_block(blocked, "execute_when", "gate", spoke_local=local)
    hits = cb.consult(blocked, spoke_local=local)
    assert len(hits) == 1 and hits[0]["block_class"] == "execute_when"
    # a lug that never blocked returns nothing
    assert cb.consult({"id": "lug-fresh", "type": "impl"}, spoke_local=local) == []


def test_record_never_raises(monkeypatch, local):  # AC4
    # force the atomic write to explode; record_block must swallow + return None
    monkeypatch.setattr(cb, "_atomic_write", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    assert cb.record_block({"id": "l", "type": "impl"}, "stall", spoke_local=local) is None


def test_summarize(local):
    cb.record_block({"id": "a"}, "execute_when", spoke_local=local)
    cb.record_block({"id": "a"}, "execute_when", spoke_local=local)
    cb.record_block({"id": "b"}, "stall", spoke_local=local)
    s = cb.summarize(local)
    assert s["total_antipatterns"] == 2
    assert s["total_occurrences"] == 3
    assert s["by_class"]["execute_when"] == 1 and s["by_class"]["stall"] == 1
