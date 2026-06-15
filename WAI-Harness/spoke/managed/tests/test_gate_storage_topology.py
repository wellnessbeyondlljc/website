#!/usr/bin/env python3
"""Verification test for impl-gate-storage-topology-v1 (test-at-birth).

Covers verify[]: patterns/ topology + per-advisor subfolders, 5 parseable flow
definitions with per-step expected_conditions, idempotent gate-log.jsonl ↔
gate_log table sync, version-anchored baselines (per-version approval rate +
new baseline on version bump), and ownership routing to the owning advisor's
patterns/ folder.
"""
import glob
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _build(db):
    r = subprocess.run([sys.executable, "tools/create_harness_db.py", "--db-path", db],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_patterns_topology_and_advisor_subfolders_exist():
    base = os.path.join(ROOT, "WAI-Spoke/patterns")
    assert os.path.isdir(os.path.join(base, "flow-definitions"))
    assert os.path.isdir(os.path.join(base, "candidates"))
    assert os.path.exists(os.path.join(base, "gate-log.jsonl"))
    assert os.path.exists(os.path.join(base, "flow-metrics.jsonl"))
    for adv in ("ozi", "historian", "expediter"):
        assert os.path.isdir(os.path.join(ROOT, "WAI-Spoke/advisors", adv, "patterns")), adv


def test_five_flow_definitions_parse_with_expected_conditions():
    fd = os.path.join(ROOT, "WAI-Spoke/patterns/flow-definitions")
    files = glob.glob(os.path.join(fd, "*.json"))
    flows = {}
    for f in files:
        d = json.load(open(f))
        flows[d["flow_id"]] = d
        assert d.get("steps"), f"{f} has no steps"
        for step in d["steps"]:
            assert step.get("expected_conditions"), f"{f} step {step.get('step_id')} has no expected_conditions"
            for ec in step["expected_conditions"]:
                assert {"check", "evidence_path", "criterion"} <= set(ec), ec
    for required in ("lug-dispatch", "teaching-import", "closeout",
                     "inbox-acceptance", "session-integrity-preflight"):
        assert required in flows, f"missing flow definition: {required}"


def test_gate_log_sync_is_idempotent():
    gls = _load("gate_log_sync")
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "h.db"); _build(db)
        jl = os.path.join(d, "gate-log.jsonl")
        with open(jl, "w") as f:
            for i in range(3):
                f.write(json.dumps({"id": f"g{i}", "flow_id": "closeout", "step_id": "tests-green",
                                    "session_id": "s1", "attempt": 1, "disposition": "approved",
                                    "evidence": "exit 0", "created_at": "2026-06-09T00:00:00"}) + "\n")
        assert gls.sync(db, jl) == 3
        con = sqlite3.connect(db)
        assert con.execute("SELECT COUNT(*) FROM gate_log").fetchone()[0] == 3
        con.close()
        # re-run: still 3 (idempotent by id PK)
        assert gls.sync(db, jl) == 0
        con = sqlite3.connect(db)
        assert con.execute("SELECT COUNT(*) FROM gate_log").fetchone()[0] == 3
        con.close()


def test_flow_metrics_per_version_and_baseline_on_bump():
    fm = _load("flow_metrics")
    with tempfile.TemporaryDirectory() as d:
        # seed events across 2 definition versions of the same flow
        events_path = os.path.join(d, "gate-log.jsonl")
        rows = [
            # v1: 1 approved of 2 terminal -> 0.5
            {"flow_id": "demo", "flow_version": 1, "step_id": "a", "attempt": 1, "disposition": "approved"},
            {"flow_id": "demo", "flow_version": 1, "step_id": "a", "attempt": 1, "disposition": "escalate"},
            # v2: 2 approved of 2 terminal -> 1.0 (improved)
            {"flow_id": "demo", "flow_version": 2, "step_id": "a", "attempt": 1, "disposition": "approved"},
            {"flow_id": "demo", "flow_version": 2, "step_id": "a", "attempt": 2, "disposition": "approved"},
        ]
        with open(events_path, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        m = fm.compute(rows)
        assert m["demo"][1]["approval_rate"] == 0.5
        assert m["demo"][2]["approval_rate"] == 1.0, "per-version, not all-time, approval"
        assert m["demo"][1]["first_attempt_approval_rate"] == 0.5
        # run twice: a baseline is anchored per (flow,version); the bump (v2) gets its own
        fd = os.path.join(d, "flow-definitions"); os.makedirs(fd)
        json.dump({"flow_id": "demo", "version": 2}, open(os.path.join(fd, "demo.json"), "w"))
        out = os.path.join(d, "flow-metrics.jsonl")
        res1 = fm.run(events_path, fd, out, now_iso="2026-06-09T00:00:00")
        assert res1["new_baselines"] == 2, "v1 and v2 each anchor a baseline"
        res2 = fm.run(events_path, fd, out, now_iso="2026-06-09T01:00:00")
        assert res2["new_baselines"] == 0, "no duplicate baselines on re-run"
        baselines = [json.loads(l) for l in open(out) if json.loads(l).get("kind") == "baseline"]
        assert len(baselines) == 2
        v2 = [b for b in baselines if b["version"] == 2][0]
        assert v2["is_current_version"] is True and v2["approval_rate"] == 1.0


def test_ownership_routes_event_to_owning_advisor_folder():
    gls = _load("gate_log_sync")
    with tempfile.TemporaryDirectory() as d:
        patterns_root = os.path.join(d, "patterns"); os.makedirs(patterns_root)
        advisors_root = os.path.join(d, "advisors")
        fd = os.path.join(d, "flow-definitions"); os.makedirs(fd)
        json.dump({"flow_id": "lug-dispatch", "owner": "ozi"}, open(os.path.join(fd, "lug.json"), "w"))
        json.dump({"flow_id": "closeout", "owner": "main-agent"}, open(os.path.join(fd, "co.json"), "w"))
        # ozi-owned flow event -> advisors/ozi/patterns/
        p1 = gls.route_event({"flow_id": "lug-dispatch", "disposition": "approved"},
                             patterns_root, advisors_root, fd)
        assert p1 == os.path.join(advisors_root, "ozi", "patterns", "gate-log.jsonl")
        assert os.path.exists(p1)
        # main-agent flow event -> top-level patterns/
        p2 = gls.route_event({"flow_id": "closeout", "disposition": "approved"},
                             patterns_root, advisors_root, fd)
        assert p2 == os.path.join(patterns_root, "gate-log.jsonl")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASS")
