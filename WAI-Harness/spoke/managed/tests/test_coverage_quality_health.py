#!/usr/bin/env python3
"""Test-at-birth for coverage + Quality Health (tools/compute_coverage.py, AC28/AC30)
and its wiring into the wakeup brief.
"""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(
        mod, os.path.join(ROOT, "tools", f"{mod}.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


C = _load("compute_coverage")
GWB = _load("generate_wakeup_brief")


def _lug(lid, acs, tests, sv=4):
    return {"id": lid, "schema_version": sv, "acceptance_criteria": acs,
            "verification_test": tests}


def test_certification_score_counts_nulls_against():
    lugs = [
        _lug("l1", ["AC1 a", "AC2 b"], [
            {"covers_ac": "AC1: a", "result": 1},
            {"covers_ac": "AC2: b", "result": 1},
        ]),
        _lug("l2", ["AC1 c"], [{"covers_ac": "AC1: c", "result": None}]),  # null
        _lug("l3", ["AC1 d"], [{"covers_ac": "AC1: d", "result": 0}]),     # fail
    ]
    h = C.aggregate_coverage(lugs)
    assert h["passes"] == 2 and h["nulls"] == 1 and h["fails"] == 1
    assert h["test_count"] == 4
    assert h["certification_score"] == round(2 / 4, 3)  # nulls + fails count against
    assert h["null_rate"] == round(1 / 4, 3)
    assert set(h["uncertified_lugs"]) == {"l2", "l3"}


def test_ac_coverage_pct():
    lugs = [_lug("l1", ["AC1 a", "AC2 b", "AC3 c"], [
        {"covers_ac": "AC1: a", "result": 1},
        {"covers_ac": "AC2: b", "result": 1},
    ])]  # AC3 uncovered
    h = C.aggregate_coverage(lugs)
    assert h["ac_coverage_pct"] == round(2 / 3, 3)
    assert h["lugs_fully_covered"] == 0


def test_fully_covered():
    lugs = [_lug("l1", ["AC1 a"], [{"covers_ac": "AC1: a", "result": 1}])]
    h = C.aggregate_coverage(lugs)
    assert h["lugs_fully_covered"] == 1
    assert h["certification_score"] == 1.0


def test_ignores_non_v4():
    lugs = [_lug("v3", ["AC1 a"], [{"covers_ac": "AC1: a", "result": 1}], sv=3)]
    h = C.aggregate_coverage(lugs)
    assert h["lug_count"] == 0


def test_empty_graceful():
    h = C.aggregate_coverage([])
    assert h["lug_count"] == 0
    assert h["certification_score"] is None


def test_read_coverage_real_spoke():
    """Against the real spoke: there are v4 lugs (enriched), so status=ok with a score."""
    h = C.read_coverage(ROOT)
    assert h["status"] == "ok"
    assert h["lug_count"] >= 20  # ~22 enriched v4 lugs
    assert 0.0 <= h["certification_score"] <= 1.0


def test_quality_health_in_brief_keys():
    import inspect
    src = inspect.getsource(GWB.main)
    assert '"quality_health": quality_health_data' in src
