#!/usr/bin/env python3
"""Tests for verify_then_define (P5) — the gate decision + force override."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import verify_then_define as vtd  # noqa: E402


def test_all_green_allows():
    r = vtd.gate({"certified": True, "foundation_ready": True, "advisors_healthy": True})
    assert r["allowed"] and not r["forced"] and r["blockers"] == []


def test_missing_check_blocks_and_names_reason():
    r = vtd.gate({"certified": False, "foundation_ready": True, "advisors_healthy": True})
    assert not r["allowed"]
    assert any("certif" in b for b in r["blockers"])


def test_force_overrides_but_records_blockers():
    r = vtd.gate({"certified": False, "foundation_ready": False, "advisors_healthy": False}, force=True)
    assert r["allowed"] and r["forced"]
    assert len(r["blockers"]) == 3  # override is logged, not silent


def test_advisor_health_gate():
    r = vtd.gate({"certified": True, "foundation_ready": True, "advisors_healthy": False})
    assert not r["allowed"] and any("advisor" in b for b in r["blockers"])
