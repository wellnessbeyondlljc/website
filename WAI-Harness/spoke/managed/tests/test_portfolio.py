#!/usr/bin/env python3
"""Tests for portfolio (P4) — initiative weight, top-aspirational pick, health-floor allocation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import portfolio as pf  # noqa: E402


def test_initiative_weight():
    assert pf.initiative_weight({"impact_rank": 1, "focus_lock": True}) == 9.0  # 3 * 3
    assert pf.initiative_weight({"impact_rank": 2}) == 2.0
    assert pf.initiative_weight({"impact_rank": 1, "lifecycle_state": "dormant"}) == 0.15
    assert pf.initiative_weight(None) == 1.0


def test_top_aspirational_picks_highest_weight():
    inits = {
        "a": {"impact_rank": 3, "flavor": "aspirational", "lifecycle_state": "active"},
        "b": {"impact_rank": 1, "focus_lock": True, "flavor": "aspirational", "lifecycle_state": "active"},
        "h": {"impact_rank": 1, "flavor": "health", "lifecycle_state": "active"},
        "d": {"impact_rank": 1, "flavor": "aspirational", "lifecycle_state": "dormant"},
    }
    assert pf.top_aspirational(inits) == "b"  # highest weight, not dormant, aspirational


def test_allocate_health_floor_then_concentrate():
    inits = {
        "asp": {"impact_rank": 1, "flavor": "aspirational", "lifecycle_state": "active"},
        "asp2": {"impact_rank": 3, "flavor": "aspirational", "lifecycle_state": "active"},
        "hea": {"impact_rank": 1, "flavor": "health", "lifecycle_state": "active"},
    }
    lugs = ([{"id": f"h{i}", "initiative": "hea"} for i in range(5)] +
            [{"id": f"a{i}", "initiative": "asp"} for i in range(5)] +
            [{"id": f"o{i}", "initiative": "asp2"} for i in range(5)])
    plan = pf.allocate(lugs, inits, budget=10, health_floor_pct=20)
    assert plan["chosen_initiative"] == "asp"
    assert plan["health_cap"] == 2  # ceil(10*0.2)
    health_dispatched = [p for p in plan["plan"] if p[1] == "health-floor"]
    assert len(health_dispatched) == 2  # floor is a CAP
    top = [p for p in plan["plan"] if p[1].startswith("top-aspirational")]
    assert len(top) == 5  # remaining budget concentrates on the top initiative


def test_allocate_no_health_work_spends_zero_on_health():
    inits = {"asp": {"impact_rank": 1, "flavor": "aspirational", "lifecycle_state": "active"}}
    lugs = [{"id": f"a{i}", "initiative": "asp"} for i in range(3)]
    plan = pf.allocate(lugs, inits, budget=10, health_floor_pct=20)
    assert not any(p[1] == "health-floor" for p in plan["plan"])  # floor is a cap, not a guarantee
    assert plan["dispatched"] == 3


def test_flat_spoke_no_initiatives_defaults_safely():
    lugs = [{"id": "x"}, {"id": "y"}]
    plan = pf.allocate(lugs, {}, budget=8)
    assert plan["dispatched"] == 2  # no initiatives -> still ranks/dispatches, no crash
