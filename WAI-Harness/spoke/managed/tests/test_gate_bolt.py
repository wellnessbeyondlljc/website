"""Acceptance proof: emit_gate_bolt + gate-certification bolt kind (AC13).
Ties Pattern-Gate dispositions (approved/halted/escalate) into the bolt substrate.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import verify_engine as ve  # noqa: E402

CHECKS = [{"check_id": "c1", "result": 1, "detail": "manifest present"},
          {"check_id": "c2", "result": 1, "detail": "no stale paths"}]


def test_gate_certification_in_schema_enum():
    schema = json.loads((ROOT / "schemas" / "bolt.schema.json").read_text())
    assert "gate-certification" in schema["properties"]["kind"]["enum"]


def test_approved_gate_certifies(tmp_path):
    b = ve.emit_gate_bolt("session-x", "lug-dispatch", "approved", CHECKS,
                          spoke_path=tmp_path, step_id="preflight", write_bolt=True)
    assert b["kind"] == "gate-certification"
    assert b["certification_status"] == "certified"
    assert b["disposition"] == "approved" and b["flow_id"] == "lug-dispatch"
    assert b["id"] == "bolt-session-x-gate-lug-dispatch-preflight"
    # written under bolts/bytype/gate-certification/recorded/
    p = Path(b["_bolt_path"])
    assert p.exists() and "gate-certification" in str(p)
    assert json.loads(p.read_text())["kind"] == "gate-certification"


def test_halt_records_partial(tmp_path):
    b = ve.emit_gate_bolt("session-y", "closeout", "halted", CHECKS, spoke_path=tmp_path)
    assert b["certification_status"] == "partial" and b["disposition"] == "halted"


def test_escalate_records_partial(tmp_path):
    b = ve.emit_gate_bolt("session-z", "teaching-import", "escalate", CHECKS, spoke_path=tmp_path)
    assert b["certification_status"] == "partial" and b["disposition"] == "escalate"


def test_gate_bolt_id_stable_idempotent(tmp_path):
    a = ve.emit_gate_bolt("s1", "inbox-acceptance", "approved", CHECKS, spoke_path=tmp_path, write_bolt=False)
    b = ve.emit_gate_bolt("s1", "inbox-acceptance", "approved", CHECKS, spoke_path=tmp_path, write_bolt=False)
    assert a["id"] == b["id"]  # stable per (session, flow, step) -> overwrites in place
