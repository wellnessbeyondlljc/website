#!/usr/bin/env python3
"""Verification test for impl-verification-spine-core-v1 (test-at-birth).

Covers verify[]: test-at-birth gate (blocks uncovered/unreviewed AC), two-pass
semantic block, fresh-actor rule, experiential bar, coverage compute, stale
detection, null disclosure, and failure routing/escalation.
"""
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


VS = _load("verification_spine")


def test_test_at_birth_blocks_uncovered_then_passes():
    # AC lacking a test (one verify step, two ACs) + unreviewed -> blocked
    lug = {"acceptance_criteria": ["ac1", "ac2"], "verify": ["checks ac1"],
           "verification_test": "tests/test_x.py"}
    g = VS.test_at_birth_gate(lug)
    assert g["ok"] is False and g["uncovered_acs"] == ["ac2"]
    assert g["gap"] == "ac-uncovered"
    # no verification_test at all -> blocked
    assert VS.test_at_birth_gate({"acceptance_criteria": ["a"], "verify": ["v"]})["ok"] is False
    # fully covered + reviewed -> passes
    good = {"acceptance_criteria": ["ac1", "ac2"], "verify": ["v1", "v2"],
            "verification_test": "tests/test_x.py", "reviewed_by": "jordy"}
    assert VS.test_at_birth_gate(good)["ok"] is True
    # covered but NOT reviewed -> still blocked (test-quality second-party rule)
    unrev = dict(good); del unrev["reviewed_by"]
    assert VS.test_at_birth_gate(unrev)["ok"] is False


def test_two_pass_semantic_blocks_count_artifact():
    # a count that passes mechanical but fails semantic -> blocked from show-user
    checks = [{"check": "runs", "mode": "mechanical", "result": 1},
              {"check": "items-right-type", "mode": "semantic", "result": 0}]
    r = VS.pre_user_gate("count", checks)
    assert r["show_user"] is False and "semantic" in r["reason"]
    # semantic passes -> allowed
    checks[1]["result"] = 1
    assert VS.pre_user_gate("count", checks)["show_user"] is True


def test_fresh_actor_rule_for_user_facing():
    checks = [{"check": "runs", "mode": "mechanical", "result": 1},
              {"check": "semantic", "mode": "semantic", "result": 1},
              {"check": "renders", "mode": "experiential", "result": 1}]
    # same actor produced + gated -> blocked
    blocked = VS.pre_user_gate("user-facing", checks, producer="opus-A", gate_actor="opus-A")
    assert blocked["show_user"] is False and "fresh-actor" in blocked["reason"]
    # distinct gate actor -> allowed
    ok = VS.pre_user_gate("user-facing", checks, producer="opus-A", gate_actor="haiku-gate")
    assert ok["show_user"] is True


def test_experiential_bar_blocks_unrendered_artifact():
    # well-formed on disk (mechanical+semantic) but no experiential render -> blocked
    checks = [{"check": "runs", "mode": "mechanical", "result": 1},
              {"check": "semantic", "mode": "semantic", "result": 1}]
    r = VS.pre_user_gate("user-facing", checks, producer="A", gate_actor="B")
    assert r["show_user"] is False and "experiential" in r["reason"]


def test_coverage_and_stale_compute():
    lugs = [{"id": "l1", "verification_test": "t1"}, {"id": "l2", "verification_test": "t2"},
            {"id": "l3"}]  # l3 has no test
    results = [{"test_id": "t1", "result": "pass", "version": 5},
               {"test_id": "t2", "result": "fail", "version": 5},
               {"test_id": "t3", "result": "null", "version": 1}]  # old -> stale
    cov = VS.compute_coverage(lugs, results, current_version=5, stale_window=2)
    assert cov["lug_coverage_pct"] == round(2 / 3, 3)
    assert cov["null_rate"] == round(1 / 3, 3)
    assert cov["certification_score"] == round(1 / 3, 3)
    assert cov["stale"] == ["t3"], "test at version 1 vs current 5 is stale"


def test_null_is_disclosed_not_silent():
    checks = [{"check": "runs", "mode": "mechanical", "result": 1},
              {"check": "edge-case", "mode": "attested", "result": "null"}]
    r = VS.pre_user_gate("mechanical", checks)
    assert r["show_user"] is True
    assert r["disclosed_nulls"] == ["edge-case"], "null gap must be disclosed, never silent done"


def test_failure_routes_and_escalates():
    fail = {"result": "fail", "owner_type": "lug", "owner_id": "impl-foo-v1"}
    r1 = VS.route_failure(fail, prior_failures=0)
    assert r1["routed"] and r1["owner"] == "impl-foo-v1" and r1["escalate"] is False
    # repeated failure past the cap escalates to Historian
    r2 = VS.route_failure(fail, prior_failures=2, cap=2)
    assert r2["escalate"] is True and r2["signal"] == "historian"
    # a pass routes nowhere
    assert VS.route_failure({"result": "pass"})["routed"] is False


def test_quality_health_and_gap_taxonomy():
    cov = VS.compute_coverage([{"verification_test": "t"}], [{"result": "pass", "version": 1}],
                              current_version=1)
    h = VS.quality_health(cov, failing_suites=["suite-x"])
    assert "coverage_pct" in h and h["failing_suites"] == ["suite-x"] and "stale_count" in h
    # the 7 typed gaps are present as data with detector + surface
    assert len(VS.GAP_TYPES) == 7
    assert all("detector" in v and "surface" in v for v in VS.GAP_TYPES.values())


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASS")
