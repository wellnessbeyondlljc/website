#!/usr/bin/env python3
"""P4 portfolio allocation — AC-mapped tests.

Covers the four acceptance criteria of impl-ozi-portfolio-allocation-v1:
  AC1 test_weight_and_dormant_zero          — initiative weight folds focus_lock/
                                              impact_rank/lifecycle; dormant ~0, never dispatch
  AC2 test_health_floor_is_cap              — health-floor is a CAP (0 spent w/ no health work)
  AC3 test_aspirational_concentration_bounded — remainder concentrates on the single top
                                              aspirational initiative, bounded by concentration max
  AC4 test_index_cached_once                — the index is loaded once per run (no per-lug read)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import portfolio as pf  # noqa: E402


# ---------- AC1 ----------

def test_weight_and_dormant_zero():
    # focus_lock (3x) * impact_rank-1 tier (3.0) * active (1.0) = 9.0
    assert pf.initiative_weight(
        {"impact_rank": 1, "focus_lock": True, "lifecycle_state": "active"}) == 9.0
    # impact_rank tier alone, no focus_lock
    assert pf.initiative_weight({"impact_rank": 2, "lifecycle_state": "active"}) == 2.0
    # dormant collapses the weight toward zero
    dorm_w = pf.initiative_weight(
        {"impact_rank": 1, "focus_lock": True, "lifecycle_state": "dormant"})
    assert dorm_w < 0.5

    # A dormant initiative's lugs never dispatch, even with budget to spare.
    inits = {
        "hot": {"impact_rank": 1, "focus_lock": True,
                "lifecycle_state": "active", "flavor": "aspirational"},
        "dz": {"impact_rank": 1, "focus_lock": True,
               "lifecycle_state": "dormant", "flavor": "aspirational"},
    }
    lugs = ([{"id": f"d{i}", "initiative": "dz"} for i in range(5)] +
            [{"id": "h1", "initiative": "hot"}])
    plan = pf.allocate(lugs, inits, budget=8)
    ids = [pid for pid, _ in plan["plan"]]
    assert "h1" in ids                                  # live work dispatches
    assert not any(i.startswith("d") for i in ids)      # dormant lugs excluded entirely


# ---------- AC2 ----------

def test_health_floor_is_cap():
    inits = {
        "H": {"impact_rank": 2, "lifecycle_state": "active", "flavor": "health"},
        "A": {"impact_rank": 1, "focus_lock": True,
              "lifecycle_state": "active", "flavor": "aspirational"},
    }
    health_lugs = [{"id": f"h{i}", "initiative": "H"} for i in range(5)]
    aspir_lugs = [{"id": f"a{i}", "initiative": "A"} for i in range(10)]

    # Health work present: health dispatches UP TO the floor cap (ceil(10*20%)=2),
    # not all 5 — the floor is a reservation cap, the rest concentrates on aspirational.
    plan = pf.allocate(health_lugs + aspir_lugs, inits, budget=10, health_floor_pct=20)
    assert plan["health_cap"] == 2
    health_floor = [pid for pid, r in plan["plan"] if r == "health-floor"]
    assert len(health_floor) == 2
    # The remaining 8 slots go to the top aspirational initiative, not more health.
    top = [pid for pid, r in plan["plan"] if r.startswith("top-aspirational")]
    assert len(top) == 8

    # No health work at all: 0 budget is spent on health (floor is a cap, not a guarantee).
    plan2 = pf.allocate(aspir_lugs, inits, budget=10, health_floor_pct=20)
    assert not any(r == "health-floor" for _, r in plan2["plan"])
    assert plan2["dispatched"] == 10   # budget fully spent on aspirational instead


# ---------- AC3 ----------

def test_aspirational_concentration_bounded():
    inits = {
        "TOP": {"impact_rank": 1, "focus_lock": True,
                "lifecycle_state": "active", "flavor": "aspirational"},
        "SEC": {"impact_rank": 2, "lifecycle_state": "active", "flavor": "aspirational"},
    }
    top_lugs = [{"id": f"t{i}", "initiative": "TOP"} for i in range(10)]
    sec_lugs = [{"id": f"s{i}", "initiative": "SEC"} for i in range(5)]

    plan = pf.allocate(top_lugs + sec_lugs, inits, budget=10, concentration_max_pct=70)
    ids = [pid for pid, _ in plan["plan"]]
    top_count = sum(1 for i in ids if i.startswith("t"))
    sec_count = sum(1 for i in ids if i.startswith("s"))

    assert plan["chosen_initiative"] == "TOP"
    assert plan["concentration_cap"] == 7
    # bounded: the top initiative cannot take all 10 slots while another waits
    assert top_count <= 7
    # the rest is NOT spread evenly nor starved — concentrated on TOP, remainder to SEC
    assert sec_count >= 3
    assert top_count > sec_count


def test_concentration_no_waste_when_alone():
    # When only the top initiative has work, it fills the whole budget (cap is a
    # ceiling on monopolization vs. OTHERS, never a reason to waste budget).
    inits = {"TOP": {"impact_rank": 1, "focus_lock": True,
                     "lifecycle_state": "active", "flavor": "aspirational"}}
    lugs = [{"id": f"t{i}", "initiative": "TOP"} for i in range(10)]
    plan = pf.allocate(lugs, inits, budget=10, concentration_max_pct=70)
    assert plan["dispatched"] == 10


# ---------- AC4 ----------

def test_index_cached_once(tmp_path, monkeypatch):
    # Build a minimal v4 spoke with one initiative and many open lugs.
    local = tmp_path / "WAI-Harness" / "spoke" / "local"
    (local / "initiatives").mkdir(parents=True)
    (local / "initiatives" / "index.json").write_text(json.dumps({"initiatives": [
        {"id": "A", "impact_rank": 1, "lifecycle_state": "active", "flavor": "aspirational"},
    ]}))
    lugdir = local / "lugs" / "bytype" / "impl" / "open"
    lugdir.mkdir(parents=True)
    for i in range(8):
        (lugdir / f"l{i}.json").write_text(json.dumps({"id": f"l{i}", "initiative": "A"}))

    calls = {"n": 0}
    real = pf._load_initiatives

    def counting(local_path):
        calls["n"] += 1
        return real(local_path)

    monkeypatch.setattr(pf, "_load_initiatives", counting)
    plan = pf.rank_spoke(str(tmp_path), budget=8)

    assert plan["open_lugs"] == 8
    # The index is read exactly once for the whole run — per-lug weight calls are
    # served from the in-memory dict, never re-reading disk.
    assert calls["n"] == 1


def test_load_policy_reads_spec_defaults():
    # The runtime policy is sourced from the spec config block (floor 20 / conc 70).
    floor, conc = pf.load_policy()
    assert floor == 20
    assert conc == 70
