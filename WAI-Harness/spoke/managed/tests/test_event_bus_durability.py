#!/usr/bin/env python3
"""Verification test for impl-event-bus-durability-v1 (test-at-birth).

Covers verify[]: schema validation, correlation chain reconstruction, decision-
before-action enforcement, durability (journal floor + idempotent replay),
legacy stream feed, and the no-silent-actor emission-completeness check.
"""
import importlib.util
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


def test_schema_validation_and_event_id_assignment():
    eb = _load("event_bus")
    with tempfile.TemporaryDirectory() as d:
        jr = os.path.join(d, "j.jsonl")
        # missing required field (no actor) -> rejected
        try:
            eb.emit({"ts": "2026-06-09T00:00:00", "type": "gate", "status": "approved"}, jr)
            assert False, "emit should reject an event missing a required field"
        except eb.EmissionError:
            pass
        # well-formed -> accepted + event_id assigned
        eid = eb.emit({"ts": "2026-06-09T00:00:00", "type": "gate",
                       "actor": "tester", "status": "approved"}, jr)
        assert eid and isinstance(eid, str)
        assert sum(1 for _ in open(jr)) == 1


def test_correlation_chain_reconstruction():
    eb = _load("event_bus"); ec = _load("explain_chain")
    with tempfile.TemporaryDirectory() as d:
        jr = os.path.join(d, "j.jsonl")
        c = eb.new_correlation()
        # goal -> queue -> dispatch -> gate -> bolt, each linked to its parent
        goal = eb.emit({"ts": "2026-06-09T00:00:01", "type": "goal", "actor": "navigator",
                        "status": "set", "correlation_id": c}, jr)
        queue = eb.child_event(goal, jr, ts="2026-06-09T00:00:02", type="queue",
                               actor="ozi", status="scored")
        disp = eb.child_event(queue, jr, ts="2026-06-09T00:00:03", type="dispatch",
                              actor="ozi", status="dispatched")
        gate = eb.child_event(disp, jr, ts="2026-06-09T00:00:04", type="gate",
                              actor="pattern-gate", status="approved")
        eb.child_event(gate, jr, ts="2026-06-09T00:00:05", type="bolt",
                       actor="session", status="pass")
        evs = ec.chain(c, jr)
        assert [e["type"] for e in evs] == ["goal", "queue", "dispatch", "gate", "bolt"], \
            f"chain not in causal order: {[e['type'] for e in evs]}"
        # parents resolve: each non-root references the prior event's id
        ids = [e["event_id"] for e in evs]
        for i in range(1, len(evs)):
            assert evs[i]["parent_event"] == ids[i - 1]


def test_decision_required_before_escalation():
    eb = _load("event_bus")
    with tempfile.TemporaryDirectory() as d:
        jr = os.path.join(d, "j.jsonl")
        c = eb.new_correlation()
        # escalation with NO preceding decision -> rejected
        try:
            eb.emit({"ts": "2026-06-09T00:00:01", "type": "escalation", "actor": "dispatcher",
                     "status": "escalate", "correlation_id": c}, jr)
            assert False, "escalation without a decision parent must be rejected"
        except eb.EmissionError:
            pass
        # a decision carrying rationale + alternatives, then the escalation links to it
        dec = eb.emit({"ts": "2026-06-09T00:00:02", "type": "decision", "actor": "dispatcher",
                       "status": "decided", "correlation_id": c,
                       "evidence": {"rationale": "3rd failure is structural",
                                    "alternatives": ["retry", "escalate"]}}, jr)
        esc = eb.child_event(dec, jr, ts="2026-06-09T00:00:03", type="escalation",
                             actor="dispatcher", status="escalate")
        assert esc, "escalation WITH a decision parent must succeed"
        # and a decision missing alternatives does not satisfy the requirement
        bad = eb.emit({"ts": "2026-06-09T00:00:04", "type": "decision", "actor": "x",
                       "status": "decided", "evidence": {"rationale": "only this"}}, jr)
        try:
            eb.child_event(bad, jr, ts="2026-06-09T00:00:05", type="rejection",
                           actor="x", status="rejected")
            assert False, "decision without alternatives must not license a flow-changing action"
        except eb.EmissionError:
            pass


def test_durability_journal_floor_and_replay():
    eb = _load("event_bus"); dw = _load("db_writer")
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "h.db"); jr = os.path.join(d, "j.jsonl"); _build(db)
        eb.emit({"ts": "2026-06-09T00:00:01", "type": "gate", "actor": "t", "status": "approved"}, jr)
        eb.emit({"ts": "2026-06-09T00:00:02", "type": "bolt", "actor": "t", "status": "pass"}, jr)
        # journal is the durable floor: events present before any DB drain
        assert sum(1 for _ in open(jr)) == 2
        assert dw.drain(db, jr) == 2
        # idempotent replay (crash mid-drain): re-drain adds nothing
        assert dw.drain(db, jr) == 0
        con = sqlite3.connect(db)
        assert con.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2
        con.close()


def test_legacy_stream_feeds_typed_event():
    eb = _load("event_bus")
    gate_row = {"flow_id": "closeout", "step_id": "commit", "disposition": "approved",
                "certifier": "pattern-gate", "ts": "2026-06-09T00:00:00", "session_id": "s1"}
    e = eb.from_legacy("gate-log", gate_row)
    assert e["type"] == "gate" and e["status"] == "approved"
    assert e["subject_ref"] == "closeout/commit"
    with tempfile.TemporaryDirectory() as d:
        jr = os.path.join(d, "j.jsonl")
        assert eb.emit(e, jr), "a mapped legacy row emits as a valid typed event"


def test_no_silent_actor_emission_completeness():
    eb = _load("event_bus")
    with tempfile.TemporaryDirectory() as d:
        jr = os.path.join(d, "j.jsonl")
        eb.emit({"ts": "2026-06-09T00:00:01", "type": "scan", "actor": "archie", "status": "done"}, jr)
        assert eb.advisor_emitted("archie", jr) is True
        # an advisor that ran but emitted nothing fails the completeness check
        assert eb.advisor_emitted("ghost-advisor", jr) is False


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASS")
