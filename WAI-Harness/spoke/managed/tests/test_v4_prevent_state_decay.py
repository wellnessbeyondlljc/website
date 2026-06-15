#!/usr/bin/env python3
"""Acceptance-proof tests for impl-v4-prevent-state-decay-hardening-v1 (test-at-birth).

AC1 completion_gate — AC-linkage mandatory at completion for parent_epic lugs.
AC2 closeout_ac_gate — blocks closeout on epic drift OR unlinked completed epic-lugs.
AC3 ownership_status — a concurrent session can tell if it is safe to commit.
"""
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


VS = _load("verification_spine")
WG = _load("worktree_guard")
GATE = _load("closeout_ac_gate")


# ---- AC1: completion gate ---------------------------------------------------

def test_completion_gate_exempt_without_parent_epic():
    assert VS.completion_gate({"id": "x"})["ok"] is True
    assert VS.completion_gate({"id": "x"})["exempt"] is True


def test_completion_gate_blocks_parent_epic_without_linkage():
    v = VS.completion_gate({"id": "x", "parent_epic": "epic-y"})
    assert v["ok"] is False and v["gap"] == "ac-unlinked"


def test_completion_gate_allows_partial_linkage():
    lug = {"id": "x", "parent_epic": "epic-y",
           "closes_epic_acs": [{"ac": "AC8", "coverage": "partial", "pending": "wiring"}]}
    assert VS.completion_gate(lug)["ok"] is True


def test_completion_gate_blocks_bare_full_without_covering_test():
    lug = {"id": "x", "parent_epic": "epic-y",
           "closes_epic_acs": [{"ac": "AC8", "coverage": "full"}],
           "verification_test": [{"name": "t", "result": 1}]}  # no covers_ac=AC8
    v = VS.completion_gate(lug)
    assert v["ok"] is False and any("AC8" in r for r in v["reasons"])


def test_completion_gate_allows_full_with_covering_test():
    lug = {"id": "x", "parent_epic": "epic-y",
           "closes_epic_acs": [{"ac": "AC8", "coverage": "full"}],
           "verification_test": [{"name": "t", "covers_ac": "AC8", "result": 1}]}
    assert VS.completion_gate(lug)["ok"] is True


# ---- AC3: ownership status --------------------------------------------------

def test_ownership_single_session_safe():
    s = WG.ownership_status("s1", live_ids=["s1"])
    assert s["safe_to_commit"] is True and s["owns_tree"] is True


def test_ownership_shared_tree_not_safe(tmp_path):
    s = WG.ownership_status("s1", repo_path=str(tmp_path),
                            mapping_path=str(tmp_path / "map.json"),
                            live_ids=["s1", "s2"])
    assert s["safe_to_commit"] is False
    assert "s2" in s["others_live"] and "NOT" in s["advice"] or "Do NOT" in s["advice"]


def test_ownership_isolated_is_safe(tmp_path):
    mp = str(tmp_path / "map.json")
    json.dump({"s1": str(tmp_path / ".worktrees" / "session-s1")}, open(mp, "w"))
    s = WG.ownership_status("s1", repo_path=str(tmp_path), mapping_path=mp,
                            live_ids=["s1", "s2"])
    assert s["safe_to_commit"] is True and s["isolated"] is True


# ---- AC2: closeout gate (tree-level) ---------------------------------------

def _spoke(tmp_path):
    base = tmp_path / "WAI-Spoke" / "lugs" / "bytype"
    (base / "epic" / "open").mkdir(parents=True)
    (base / "impl" / "completed").mkdir(parents=True)
    return tmp_path


def _write(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(d, open(p, "w"))


def test_closeout_gate_pass_when_clean(tmp_path):
    root = _spoke(tmp_path)
    # epic with one AC, box matches evidence ([~] partial) from a linked lug
    _write(str(root / "WAI-Spoke/lugs/bytype/epic/open/epic-y.json"),
           {"id": "epic-y", "status": "open",
            "acceptance_criteria_status": ["[~] AC1 do a thing"]})
    _write(str(root / "WAI-Spoke/lugs/bytype/impl/completed/impl-a.json"),
           {"id": "impl-a", "status": "completed", "parent_epic": "epic-y",
            "closes_epic_acs": [{"ac": "AC1", "coverage": "partial", "pending": "rest"}]})
    res = GATE.run(str(root))
    assert res["ok"] is True


def test_closeout_gate_blocks_on_drift(tmp_path):
    root = _spoke(tmp_path)
    # box says done [x] but no lug evidence -> over_report drift
    _write(str(root / "WAI-Spoke/lugs/bytype/epic/open/epic-y.json"),
           {"id": "epic-y", "status": "open",
            "acceptance_criteria_status": ["[x] AC1 do a thing"]})
    res = GATE.run(str(root))
    assert res["ok"] is False and "epic-y" in res["drift"]["drift_by_epic"]


def test_closeout_gate_blocks_on_unlinked_completed_lug(tmp_path):
    root = _spoke(tmp_path)
    _write(str(root / "WAI-Spoke/lugs/bytype/epic/open/epic-y.json"),
           {"id": "epic-y", "status": "open",
            "acceptance_criteria_status": ["[ ] AC1 do a thing"]})
    # a completed parent_epic lug with NO closes_epic_acs
    _write(str(root / "WAI-Spoke/lugs/bytype/impl/completed/impl-b.json"),
           {"id": "impl-b", "status": "completed", "parent_epic": "epic-y"})
    res = GATE.run(str(root))
    assert res["ok"] is False
    assert any(v["lug"] == "impl-b" for v in res["linkage"]["violations"])
