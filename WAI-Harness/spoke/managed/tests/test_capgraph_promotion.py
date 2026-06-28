#!/usr/bin/env python3
"""Tests for capgraph_blocks P2 — spoke->hub promotion + expediter pre-emption.

AC1: A structural antipattern at occurrences>=N emits exactly one change-lug to Basher
     and stamps promoted_at (idempotent across reruns).
AC2: Transient dispatch_failure blocks are never promoted regardless of occurrences.
AC3: expediter consult routes a lug matching a known unresolved antipattern to tender
     before dispatch.
AC4: A promoted antipattern distributed to a second spoke is present in its
     capabilities-effective.json and pre-empts there via consult().
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import capgraph_blocks as cb  # noqa: E402
import spoke_expediter as se  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def local(tmp_path):
    """Minimal spoke root with WAI-Harness/spoke/local and a fake Basher spoke."""
    spoke_local = tmp_path / "WAI-Harness" / "spoke" / "local"
    (spoke_local / "capabilitygraph").mkdir(parents=True)
    (spoke_local / "lugs" / "outgoing").mkdir(parents=True)

    # Fake Basher spoke (sibling of tmp_path)
    basher_path = tmp_path / "_basher_spoke"
    basher_incoming = basher_path / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming"
    basher_incoming.mkdir(parents=True)

    # hub-registry.json so _find_basher_incoming can resolve basher
    hub_dir = tmp_path / "hub" / "local"
    hub_dir.mkdir(parents=True)
    (hub_dir / "hub-registry.json").write_text(json.dumps({
        "wheels": [{"wheel_id": "basher", "path": str(basher_path)}]
    }))

    # WAI-State.json so we can resolve hub_path
    (spoke_local / "WAI-State.json").write_text(json.dumps({
        "wheel": {"hub_path": str(tmp_path / "hub")}
    }))

    return str(tmp_path)  # pass root; _find_spoke_local resolves spoke/local


def _graph(root):
    gp = Path(root) / "WAI-Harness" / "spoke" / "local" / "capabilities-graph-local.json"
    return json.loads(gp.read_text())


def _basher_incoming(root):
    return Path(root) / "_basher_spoke" / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming"


# ---------------------------------------------------------------------------
# AC1: structural antipattern promoted exactly once
# ---------------------------------------------------------------------------

def test_promote_once_structural(local):
    """AC1: occurrences>=N + structural class → one change-lug, promoted_at stamped, idempotent."""
    lug = {"id": "lug-structural", "type": "impl"}
    # Hit N times (default threshold = 3)
    for _ in range(cb.PROMOTE_THRESHOLD):
        cb.record_block(lug, "execute_when", "all_completed: dep not done", spoke_local=local)

    graph = _graph(local)
    entry = next(e for e in graph["entries"] if e["kind"] == "antipattern")
    assert entry["occurrences"] == cb.PROMOTE_THRESHOLD
    assert "promoted_at" in entry, "promoted_at should be stamped after reaching threshold"

    # Exactly one change-lug in Basher incoming
    incoming = _basher_incoming(local)
    change_lugs = list(incoming.glob("change-capgraph-promote-*.json"))
    assert len(change_lugs) == 1, f"expected 1 change-lug, got {len(change_lugs)}"

    cl = json.loads(change_lugs[0].read_text())
    assert cl["type"] == "change"
    assert cl["routed_to"] == "SPOKE/basher"
    assert cl["antipattern_entry"]["block_class"] == "execute_when"
    assert cl["antipattern_entry"]["tier"] == "recommended"

    # Idempotent: more occurrences must NOT emit a second change-lug
    cb.record_block(lug, "execute_when", "all_completed: dep not done", spoke_local=local)
    change_lugs_after = list(incoming.glob("change-capgraph-promote-*.json"))
    assert len(change_lugs_after) == 1, "second promotion should be suppressed (promoted_at stamp)"


# ---------------------------------------------------------------------------
# AC2: transient dispatch_failure never promoted
# ---------------------------------------------------------------------------

def test_no_promote_transient(local):
    """AC2: dispatch_failure occurrences >=N must NOT emit a change-lug."""
    lug = {"id": "lug-transient", "type": "impl"}
    threshold = cb.PROMOTE_THRESHOLD
    for _ in range(threshold + 2):  # well above threshold
        cb.record_block(lug, "dispatch_failure", error_code="rc=1", spoke_local=local)

    graph = _graph(local)
    entry = next(e for e in graph["entries"] if e["kind"] == "antipattern")
    assert entry["occurrences"] >= threshold
    assert "promoted_at" not in entry, "dispatch_failure must never be promoted"

    incoming = _basher_incoming(local)
    change_lugs = list(incoming.glob("change-capgraph-promote-*.json"))
    assert len(change_lugs) == 0, "no change-lug should be emitted for transient dispatch_failure"


def test_no_promote_stall(local):
    """AC2 extension: stall (also transient) must not be promoted."""
    lug = {"id": "lug-stall", "type": "impl"}
    for _ in range(cb.PROMOTE_THRESHOLD + 1):
        cb.record_block(lug, "stall", "consecutive failures", spoke_local=local)

    graph = _graph(local)
    entry = next(e for e in graph["entries"] if e["kind"] == "antipattern")
    assert "promoted_at" not in entry
    assert len(list(_basher_incoming(local).glob("change-capgraph-promote-*.json"))) == 0


# ---------------------------------------------------------------------------
# AC3: expediter consult pre-empts at dispatch
# ---------------------------------------------------------------------------

def test_expediter_preempt(local):
    """AC3: a lug with an open local antipattern is routed to tender before dispatch."""
    lug = {
        "id": "lug-preempt",
        "type": "impl",
        "model_fit": "SONNET",
        "routed_to": "LOCAL",
        "quality_score": 8,
    }

    # Record enough blocks to create the antipattern (but below promote threshold
    # to keep the test simple — promotion is irrelevant to pre-emption)
    for _ in range(2):
        cb.record_block(lug, "execute_when", "gate not cleared", spoke_local=local)

    # assign_execution_mode should pick up the open antipattern via consult()
    quality = 8
    all_open = [lug]
    mode, substrate, hint = se.assign_execution_mode(lug, quality, all_open, local)

    assert mode == "tender", f"expected tender but got {mode}"
    assert hint is not None and "capgraph" in hint.lower(), f"hint should mention capgraph: {hint}"


def test_expediter_no_preempt_when_resolved(local):
    """AC3 negative: a RESOLVED antipattern must NOT pre-empt dispatch."""
    lug = {
        "id": "lug-resolved",
        "type": "impl",
        "model_fit": "SONNET",
        "routed_to": "LOCAL",
    }
    sig = cb.record_block(lug, "execute_when", "gate", spoke_local=local)
    assert sig is not None
    cb.set_resolution(sig, "rung-1: substitute found", spoke_local=local)

    mode, _, _ = se.assign_execution_mode(lug, 8, [lug], local)
    # Should NOT be pre-empted since antipattern is resolved
    assert mode != "tender" or "capgraph" not in (str(mode) + str(_)), \
        "resolved antipattern should not pre-empt"


# ---------------------------------------------------------------------------
# AC4: fleet-distributed antipattern pre-empts on a second spoke
# ---------------------------------------------------------------------------

def _write_effective_graph(root, entries):
    """Write a fake capabilities-effective.json to simulate fleet distribution."""
    eff_dir = Path(root) / "WAI-Harness" / "spoke" / "managed" / "runtime"
    eff_dir.mkdir(parents=True, exist_ok=True)
    (eff_dir / "capabilities-effective.json").write_text(json.dumps({
        "entries": entries,
        "decisions": [],
        "resolved_count": len(entries),
    }))


def test_fleet_preempt(local):
    """AC4: antipattern in capabilities-effective.json pre-empts matching lug via consult()."""
    # Simulate a fleet-distributed antipattern (promoted from another spoke)
    fleet_antipattern = {
        "id": "ap-block:precondition_unmet:other-spoke-lug-x",
        "kind": "antipattern",
        "tier": "recommended",
        "block_class": "precondition_unmet",
        "status": "open",
        "source": "hub",
        "situation": {"lug_type": "impl", "target": "missing prereq file"},
        "solution": None,
        "resolution": None,
        "occurrences": 5,
        "sources": ["other-spoke-lug-x"],
    }
    _write_effective_graph(local, [fleet_antipattern])

    # A local lug of the same type that has never been blocked locally
    lug = {
        "id": "lug-fresh-on-this-spoke",
        "type": "impl",
        "model_fit": "SONNET",
        "routed_to": "LOCAL",
    }

    hits = cb.consult(lug, spoke_local=local)
    assert len(hits) >= 1, "fleet antipattern should be surfaced by consult()"
    assert hits[0]["block_class"] == "precondition_unmet"

    # Verify expediter also pre-empts
    mode, _, hint = se.assign_execution_mode(lug, 8, [lug], local)
    assert mode == "tender", f"fleet antipattern should pre-empt to tender, got {mode}"
    assert "capgraph" in (hint or "").lower()


def test_fleet_preempt_transient_not_distributed(local):
    """AC4 negative: a transient (stall) antipattern in effective graph is NOT matched."""
    fleet_antipattern = {
        "id": "ap-block:stall:other-spoke-lug-y",
        "kind": "antipattern",
        "tier": "recommended",
        "block_class": "stall",  # transient — not in STRUCTURAL_CLASSES
        "status": "open",
        "source": "hub",
        "situation": {"lug_type": "impl", "target": "2 consecutive stalls"},
        "solution": None,
        "resolution": None,
        "occurrences": 4,
        "sources": ["other-spoke-lug-y"],
    }
    _write_effective_graph(local, [fleet_antipattern])

    lug = {"id": "lug-not-preempted", "type": "impl", "model_fit": "SONNET", "routed_to": "LOCAL"}
    hits = cb.consult(lug, spoke_local=local)
    # stall is not in STRUCTURAL_CLASSES so it must NOT be surfaced by fleet consult
    stall_hits = [h for h in hits if h.get("block_class") == "stall"]
    assert len(stall_hits) == 0, "transient (stall) fleet antipatterns must not pre-empt"


# ---------------------------------------------------------------------------
# count_dispatchable integration
# ---------------------------------------------------------------------------

def test_count_dispatchable_excludes_capgraph_blocked(local):
    """P2 wiring: a lug with capgraph_blocked=True via _is_blocked propagation is excluded."""
    # scored item with blocked=True (set when _capgraph_blocked was True on the lug)
    scored = [
        {
            "id": "a", "model_fit": "sonnet", "execution_mode": "tender",
            "blocked": True,  # capgraph-blocked
            "type": "impl",
        },
        {
            "id": "b", "model_fit": "sonnet", "execution_mode": "subagent",
            "blocked": False,
            "type": "impl",
        },
    ]
    dispatchable = se.count_dispatchable(scored)
    ids = [s["id"] for s in dispatchable]
    assert "a" not in ids, "capgraph-blocked lug must not be dispatchable"
    assert "b" in ids, "normal lug must still be dispatchable"
