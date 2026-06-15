#!/usr/bin/env python3
"""Test-at-birth for AC8 — wakeup Pattern Health wiring into generate_wakeup_brief.py.

The originating session flagged AC8 as built-but-unwired: pattern_health() existed
and was tested, but the wakeup brief did not render the section. This verifies the
wiring: read_pattern_health() computes the section from the gate-log + candidates,
degrades gracefully when there is no gate-log, and feeds the brief.
"""
import importlib.util
import json
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(
        mod, os.path.join(ROOT, "tools", f"{mod}.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


GWB = _load("generate_wakeup_brief")
from pathlib import Path


def _spoke_with_gatelog(d, events):
    spoke = Path(d) / "WAI-Spoke"
    (spoke / "patterns").mkdir(parents=True)
    (spoke / "advisors" / "historian" / "patterns" / "candidates").mkdir(parents=True)
    gl = spoke / "patterns" / "gate-log.jsonl"
    gl.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return spoke


def test_pattern_health_computes_from_gatelog():
    events = [
        {"flow_id": "closeout-v1", "step_id": "s1", "disposition": "approved", "attempt": 1},
        {"flow_id": "closeout-v1", "step_id": "s2", "disposition": "halted", "attempt": 1},
        {"flow_id": "closeout-v1", "step_id": "s2", "disposition": "halted", "attempt": 1},
        {"flow_id": "closeout-v1", "step_id": "s2", "disposition": "approved", "attempt": 2},
    ]
    with tempfile.TemporaryDirectory() as d:
        spoke = _spoke_with_gatelog(d, events)
        h = GWB.read_pattern_health(spoke)
        assert h["status"] == "ok"
        assert h["event_count"] == 4
        # closeout-v1: 2 terminal approvals, 1 first-attempt -> 0.5
        assert h["first_attempt_approval_rate"]["closeout-v1"] == 0.5
        assert h["halt_frequency_per_step"]["closeout-v1/s2"] == 2
        assert h["open_candidates"] == 0


def test_pattern_health_counts_candidates():
    with tempfile.TemporaryDirectory() as d:
        spoke = _spoke_with_gatelog(d, [{"flow_id": "f", "step_id": "s", "disposition": "approved", "attempt": 1}])
        cand = spoke / "advisors" / "historian" / "patterns" / "candidates"
        (cand / "cand-1.json").write_text("{}")
        (cand / "cand-2.json").write_text("{}")
        h = GWB.read_pattern_health(spoke)
        assert h["open_candidates"] == 2


def test_pattern_health_no_gatelog_graceful():
    with tempfile.TemporaryDirectory() as d:
        spoke = Path(d) / "WAI-Spoke"
        (spoke).mkdir(parents=True)
        h = GWB.read_pattern_health(spoke)
        assert h is not None
        assert h["status"] == "no-gate-log-yet"
        assert h["open_candidates"] == 0


def test_pattern_health_in_brief_keys():
    """The brief dict must carry a 'pattern_health' key (the section now renders)."""
    import inspect
    src = inspect.getsource(GWB.main)
    assert '"pattern_health": pattern_health_data' in src, "brief must include pattern_health"


def test_unreadable_gatelog_graceful():
    with tempfile.TemporaryDirectory() as d:
        spoke = Path(d) / "WAI-Spoke"
        (spoke / "patterns").mkdir(parents=True)
        (spoke / "patterns" / "gate-log.jsonl").write_text("{not valid json\n")
        h = GWB.read_pattern_health(spoke)
        assert h["status"] == "unreadable"
