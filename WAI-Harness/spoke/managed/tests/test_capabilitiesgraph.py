#!/usr/bin/env python3
"""Acceptance-proof tests for impl-capabilitiesgraph-evaluator-v1 (test-at-birth).

Covers spec-capabilitiesgraph-v1 (inheritance axes + gap_computation) + the impl
lug's verification_test[]. Core logic is pure functions over synthetic layers, so
these tests do not depend on the MyWheel master tree.
"""
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MYWHEEL = "/home/mario/projects/wheelwright/mywheel"


def _load(mod):
    spec = importlib.util.spec_from_file_location(
        mod, os.path.join(ROOT, "tools", f"{mod}.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = _load("resolve_capabilities_graph")
G = _load("compute_capability_gaps")


def _hub_entry(cid, tier="mandated", **over):
    e = {"id": cid, "name": cid, "kind": "behavior", "tier": tier,
         "situation": "s", "solution": "sol", "verification_ref": "t",
         "file_paths": ["f"], "requires_tools": []}
    e.update(over)
    return e


# --------------------------- resolver ------------------------------------- #

def test_resolve_merges_layers():
    layers = [
        {"source": "hub", "entries": [_hub_entry("a"), _hub_entry("b", tier="recommended"),
                                       _hub_entry("c", tier="awareness")]},
        {"source": "local", "entries": [{"id": "d", "tier": "recommended", "situation": "x",
                                          "solution": "y"}]},
    ]
    res = R.resolve_capabilities_graph(layers)
    ids = {e["id"] for e in res["entries"]}
    assert ids == {"a", "b", "c", "d"}
    for e in res["entries"]:
        assert e["inheritance_trace"], f"{e['id']} has no inheritance_trace"
    d = next(e for e in res["entries"] if e["id"] == "d")
    assert d["source"] == "local"


def test_mandated_behavior_block():
    layers = [
        {"source": "hub", "entries": [_hub_entry("a", tier="mandated")]},
        {"source": "local", "entries": [{"id": "a", "tier": "recommended"}]},  # try to weaken
    ]
    res = R.resolve_capabilities_graph(layers)
    a = next(e for e in res["entries"] if e["id"] == "a")
    assert a["tier"] == "mandated", "hub-mandated tier must survive a local weakening attempt"
    assert any(d["kind"] == "mandated-override-blocked" and d["capability"] == "a"
               for d in res["decisions"])
    assert any(t["action"] == "blocked" for t in a["inheritance_trace"])


def test_config_axis_local_wins():
    layers = [
        {"source": "hub", "entries": [_hub_entry("a", tier="recommended",
                                                  run={"trigger": "on-entry", "auto": True})]},
        {"source": "local", "entries": [{"id": "a", "run": {"trigger": "scheduled", "auto": False}}]},
    ]
    res = R.resolve_capabilities_graph(layers)
    a = next(e for e in res["entries"] if e["id"] == "a")
    assert a["run"]["trigger"] == "scheduled", "local wins on the config axis"
    assert any(t["axis"] == "config" and t["action"] == "overridden" for t in a["inheritance_trace"])


def test_local_mandated_downgraded():
    layers = [
        {"source": "hub", "entries": []},
        {"source": "local", "entries": [{"id": "z", "tier": "mandated", "situation": "s",
                                          "solution": "sol"}]},
    ]
    res = R.resolve_capabilities_graph(layers)
    z = next(e for e in res["entries"] if e["id"] == "z")
    assert z["tier"] == "recommended", "a local NEW mandated entry must be downgraded"
    assert any(d["kind"] == "mandated-downgrade" and d["capability"] == "z" for d in res["decisions"])


# --------------------------- gap computer --------------------------------- #

def _bar():
    return [
        _hub_entry("m1", tier="mandated"),
        _hub_entry("m2", tier="mandated"),
        _hub_entry("mtool", tier="mandated", requires_tools=["supabase-rest"]),
        _hub_entry("r1", tier="recommended"),
        _hub_entry("r2", tier="recommended", status="declined",
                   decision_rationale="not needed here"),
        _hub_entry("aw", tier="awareness"),
    ]


def test_gap_mandated_absent():
    survey = {"m2": {"present": True, "certified": True}, "mtool": {"present": True, "certified": True},
              "r1": {"present": True, "certified": True}}
    am = ["supabase-rest"]
    r = G.compute_capability_gaps(_bar(), survey, am)
    types = {(g["capability"], g["type"]) for g in r["blocking"]}
    assert ("m1", "capability-missing") in types


def test_gap_mandated_loose():
    survey = {"m1": {"present": True, "certified": True},
              "m2": {"present": True, "certified": False},  # loose
              "mtool": {"present": True, "certified": True}}
    am = ["supabase-rest"]
    r = G.compute_capability_gaps(_bar(), survey, am)
    assert ("m2", "test-null") in {(g["capability"], g["type"]) for g in r["blocking"]}


def test_gap_tool_missing():
    survey = {"m1": {"present": True, "certified": True}, "m2": {"present": True, "certified": True},
              "mtool": {"present": True, "certified": True}}
    am = []  # supabase-rest NOT available
    r = G.compute_capability_gaps(_bar(), survey, am)
    tool_gaps = [g for g in r["blocking"] if g["type"] == "tool-missing"]
    assert tool_gaps and tool_gaps[0]["capability"] == "mtool"
    assert "supabase-rest" in tool_gaps[0]["missing_tool"]


def test_gap_recommended_and_declined():
    survey = {"m1": {"present": True, "certified": True}, "m2": {"present": True, "certified": True},
              "mtool": {"present": True, "certified": True}}  # r1 absent, r2 declined, aw absent
    am = ["supabase-rest"]
    r = G.compute_capability_gaps(_bar(), survey, am)
    assert any(g["capability"] == "r1" for g in r["soft"])
    assert any(g["capability"] == "r2" for g in r["declined"])
    assert not any(g["capability"] == "aw" for g in r["soft"] + r["blocking"])


def test_roadmap_ordered():
    survey = {}  # everything absent
    am = []
    r = G.compute_capability_gaps(_bar(), survey, am)
    prios = [step["priority"] for step in r["roadmap"]]
    # all P1-blocking come before any P2-recommended
    last_p1 = max((i for i, p in enumerate(prios) if p == "P1-blocking"), default=-1)
    first_p2 = min((i for i, p in enumerate(prios) if p == "P2-recommended"), default=len(prios))
    assert last_p1 < first_p2, f"roadmap not ordered: {prios}"


def test_survey_as_set():
    """The simple case: survey as a set of present-and-certified ids."""
    r = G.compute_capability_gaps(_bar(), {"m1", "m2", "mtool"}, ["supabase-rest"])
    assert any(g["capability"] == "r1" for g in r["soft"])
    assert not any(g["capability"] in ("m1", "m2") for g in r["blocking"])


# --------------------------- seed schema ---------------------------------- #

def test_seed_hub_cg_valid():
    p = os.path.join(MYWHEEL, "WAI-Harness/hub/managed/capabilities-graph-hub.json")
    if not os.path.exists(p):
        import pytest
        pytest.skip("seed hub CG not present (master tree not seeded in this env)")
    data = json.load(open(p))
    entries = data["entries"]
    assert len(entries) >= 6
    valid_tiers = {"mandated", "recommended", "awareness"}
    for e in entries:
        for req in ("id", "name", "kind", "tier", "situation", "solution", "source"):
            assert e.get(req), f"{e.get('id')} missing {req}"
        assert e["tier"] in valid_tiers
        if e["tier"] == "mandated":
            assert e.get("file_paths"), f"mandated {e['id']} must carry file_paths"
            assert e.get("verification_ref"), f"mandated {e['id']} must carry verification_ref"


def test_resolve_from_seed_tree():
    """End-to-end: resolve the real seeded hub CG (if present)."""
    p = os.path.join(MYWHEEL, "WAI-Harness/hub/managed/capabilities-graph-hub.json")
    if not os.path.exists(p):
        import pytest
        pytest.skip("seed hub CG not present")
    res = R.resolve_from_tree(MYWHEEL)
    assert len(res["entries"]) >= 6
    assert all(e.get("inheritance_trace") for e in res["entries"])
