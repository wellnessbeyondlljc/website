"""Test-at-birth for impl-derive-epic-ac-status-v1 (tools/reconcile_epic_acs.py).

Synthetic fixtures are the authoritative AC coverage; the live dogfood is a
separate evidence-grounded report (reality moved past the S46 snapshot when this
session placed the v4 .claude touchpoints).

  AC1 under-report: box [ ] but a completed lug + green covering test -> drift under_report
  AC2 over-report:  box [x] but no completed lug / null|fail test -> drift over_report
  AC3 aligned:      box matches evidence -> drift none
  AC4 attribution:  lug.closes_epic_acs links a lug to the epic AC it satisfies
  AC8 mis_partial:  completed lug + green test but coverage:partial -> [~], never [x]
  AC9 scope+fresh:  sibling-AC test does not credit this AC; a stale test -> partial
  AC10 propose-only: reconcile writes nothing; apply appends to ac_reconciliations
"""
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import reconcile_epic_acs as rec

NOW = 1_780_000_000.0
RECENT = "2026-06-09T00:00:00Z"   # we pass now via the same clock in helpers below


def _iso(epoch):
    return rec.datetime.fromtimestamp(epoch, rec.timezone.utc).isoformat()


def _epic(acs, status="open", recs=None):
    return {"id": "epic-x", "status": status, "acceptance_criteria_status": acs,
            "ac_reconciliations": recs or []}


def _lug(lid, closes, vt=None, status="completed", completed_at=None):
    return {"id": lid, "status": status, "schema_version": 4,
            "closes_epic_acs": closes,
            "verification_test": vt or [],
            "completed_at": completed_at or _iso(NOW - 3600)}


def _green(ac):
    return {"covers_ac": ac, "result": 1, "mode": "mechanical"}


# --- AC1 -------------------------------------------------------------------

def test_detects_under_report():
    epic = _epic(["[ ] AC1 the thing"])
    lugs = [_lug("impl-a", [{"ac": "AC1", "coverage": "full"}], [_green("AC1")])]
    v = rec.reconcile_acs(epic, lugs, now=NOW)[0]
    assert v["evidence_status"] == "full"
    assert v["drift_kind"] == "under_report"
    assert v["drift"] is True
    assert v["proposed_checkbox"] == "[x]"
    assert "impl-a" in v["closing_lugs"]


# --- AC2 -------------------------------------------------------------------

def test_detects_over_report():
    # box [x] but no closing lug at all
    epic = _epic(["[x] AC2 claimed done"])
    v = rec.reconcile_acs(epic, [], now=NOW)[0]
    assert v["evidence_status"] == "none"
    assert v["drift_kind"] == "over_report"
    # box [x] but the covering test is null (not green) -> evidence partial, still drift
    epic2 = _epic(["[x] AC2 claimed done"])
    lugs = [_lug("impl-b", [{"ac": "AC2", "coverage": "full"}],
                 [{"covers_ac": "AC2", "result": None, "mode": "mechanical"}])]
    v2 = rec.reconcile_acs(epic2, lugs, now=NOW)[0]
    assert v2["evidence_status"] == "partial"
    assert v2["drift_kind"] == "mis_partial"


# --- AC3 -------------------------------------------------------------------

def test_no_drift_when_aligned():
    epic = _epic(["[x] AC3 done", "[ ] AC4 not started", "[~] AC5 partial"])
    lugs = [
        _lug("impl-c", [{"ac": "AC3", "coverage": "full"}], [_green("AC3")]),
        _lug("impl-d", [{"ac": "AC5", "coverage": "partial", "pending": "wiring"}]),
    ]
    verdicts = {v["ac"]: v for v in rec.reconcile_acs(epic, lugs, now=NOW)}
    assert verdicts["AC3"]["drift_kind"] == "none"   # full <-> [x]
    assert verdicts["AC4"]["drift_kind"] == "none"   # none <-> [ ]
    assert verdicts["AC5"]["drift_kind"] == "none"   # partial <-> [~]
    assert all(not v["drift"] for v in verdicts.values())


# --- AC4 -------------------------------------------------------------------

def test_closes_epic_acs_link():
    epic = _epic(["[ ] AC7 wired"])
    # string entry = sugar for coverage:full
    lugs = [_lug("impl-e", ["AC7"], [_green("AC7")])]
    v = rec.reconcile_acs(epic, lugs, now=NOW)[0]
    assert v["closing_lugs"] == ["impl-e"]
    assert v["evidence_status"] == "full"
    # a lug that does NOT close AC7 contributes nothing
    other = [_lug("impl-f", [{"ac": "AC99", "coverage": "full"}], [_green("AC99")])]
    v2 = rec.reconcile_acs(epic, other, now=NOW)[0]
    assert v2["closing_lugs"] == []
    assert v2["evidence_status"] == "none"


# --- AC8 -------------------------------------------------------------------

def test_partial_coverage_is_tilde_not_x():
    # completed lug + GREEN test, but coverage declared partial (built-not-wired):
    # must NOT promote to [x]; box [x] over the partial evidence is mis_partial
    epic = _epic(["[x] AC8 wakeup wiring"])
    lugs = [_lug("impl-g", [{"ac": "AC8", "coverage": "partial",
                             "pending": "not wired into generate_wakeup_brief.py"}],
                 [_green("AC8")])]
    v = rec.reconcile_acs(epic, lugs, now=NOW)[0]
    assert v["evidence_status"] == "partial"          # green test does NOT make it full
    assert v["proposed_checkbox"] == "[~]"
    assert v["drift_kind"] == "mis_partial"
    assert any("wired" in p for p in v["pending"])


# --- AC9 -------------------------------------------------------------------

def test_scope_and_freshness_guards():
    # scope: a test whose covers_ac names a SIBLING AC does not credit this AC
    epic = _epic(["[ ] AC10 end-state"])
    sibling = [_lug("impl-h", [{"ac": "AC10", "coverage": "full"}],
                    [_green("AC11")])]   # green test is for AC11, not AC10
    v = rec.reconcile_acs(epic, sibling, now=NOW)[0]
    assert v["evidence_status"] == "partial"   # full claimed but no scope-correct green test
    assert v["drift_kind"] == "mis_partial"

    # freshness: a covering test older than the window counts as partial, not full
    stale = [_lug("impl-i", [{"ac": "AC10", "coverage": "full"}],
                  [{"covers_ac": "AC10", "result": 1, "mode": "mechanical",
                    "result_ts": _iso(NOW - 90 * 86400)}],
                  completed_at=_iso(NOW - 90 * 86400))]
    v2 = rec.reconcile_acs(epic, stale, now=NOW, freshness_days=30)[0]
    assert v2["evidence_status"] == "partial"

    # control: a fresh, scope-correct green test IS full
    fresh = [_lug("impl-j", [{"ac": "AC10", "coverage": "full"}],
                  [{"covers_ac": "AC10", "result": 1, "mode": "mechanical",
                    "result_ts": _iso(NOW - 3600)}])]
    v3 = rec.reconcile_acs(epic, fresh, now=NOW, freshness_days=30)[0]
    assert v3["evidence_status"] == "full"


# --- AC10 ------------------------------------------------------------------

def test_proposes_does_not_autowrite():
    epic = _epic(["[ ] AC1 done-but-unchecked"])
    lugs = [_lug("impl-k", ["AC1"], [_green("AC1")])]
    verdicts = rec.reconcile_acs(epic, lugs, now=NOW)
    # reconcile mutated nothing on the epic
    assert epic["acceptance_criteria_status"] == ["[ ] AC1 done-but-unchecked"]
    assert epic["ac_reconciliations"] == []
    # apply APPENDS to ac_reconciliations, does not overwrite, does not flip a box
    new_epic = rec.apply_reconciliation(epic, verdicts, applied_by="test")
    assert len(new_epic["ac_reconciliations"]) == 1
    assert new_epic["acceptance_criteria_status"] == ["[ ] AC1 done-but-unchecked"]  # box untouched
    assert epic["ac_reconciliations"] == []   # original object not mutated
    # a second apply appends, never overwrites
    newer = rec.apply_reconciliation(new_epic, verdicts, applied_by="test2")
    assert len(newer["ac_reconciliations"]) == 2


def test_apply_refuses_non_open_epic():
    epic = _epic(["[ ] AC1 x"], status="completed")
    try:
        rec.apply_reconciliation(epic, [])
        assert False, "should have refused a completed/historical epic"
    except ValueError as e:
        assert "P12" in str(e)


# --- drift summary + wakeup surface shape ----------------------------------

def test_wakeup_surface_ac_drift(tmp_path):
    # read_ac_drift scans open epics + lugs and returns per-epic drift counts
    spoke = tmp_path / "WAI-Spoke"
    epic_dir = spoke / "lugs" / "bytype" / "epic" / "open"
    epic_dir.mkdir(parents=True)
    (epic_dir / "epic-x.json").write_text(json.dumps({
        "id": "epic-x", "status": "open",
        "acceptance_criteria_status": ["[ ] AC1 done-but-unchecked", "[x] AC2 aligned"]}))
    impl_dir = spoke / "lugs" / "bytype" / "implementation" / "completed"
    impl_dir.mkdir(parents=True)
    (impl_dir / "l1.json").write_text(json.dumps(
        _lug("l1", ["AC1"], [_green("AC1")])))         # AC1 under_report
    (impl_dir / "l2.json").write_text(json.dumps(
        _lug("l2", ["AC2"], [_green("AC2")])))         # AC2 aligned (full <-> [x])
    drift = rec.read_ac_drift(str(tmp_path), now=NOW)
    assert "epic-x" in drift
    assert drift["epic-x"]["under_report"] == 1
    assert drift["epic-x"]["total_drift"] == 1
    # and generate_wakeup_brief exposes read_ac_drift + an ac_drift brief key
    import importlib.util, os
    root = str(Path(__file__).resolve().parents[1])
    spec = importlib.util.spec_from_file_location(
        "gwb_drift", os.path.join(root, "tools", "generate_wakeup_brief.py"))
    gwb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gwb)
    assert hasattr(gwb, "read_ac_drift")
    assert gwb.read_ac_drift(spoke) == drift


def test_closeout_gate_blocks_on_drift(tmp_path):
    # AC5 helper: has_unresolved_drift is True while an epic drifts, False when aligned
    spoke = tmp_path / "WAI-Spoke"
    epic_dir = spoke / "lugs" / "bytype" / "epic" / "open"
    epic_dir.mkdir(parents=True)
    (epic_dir / "e.json").write_text(json.dumps({
        "id": "e", "status": "open",
        "acceptance_criteria_status": ["[ ] AC1 x"]}))
    impl = spoke / "lugs" / "bytype" / "implementation" / "completed"
    impl.mkdir(parents=True)
    (impl / "l.json").write_text(json.dumps(_lug("l", ["AC1"], [_green("AC1")])))
    assert rec.has_unresolved_drift(str(tmp_path), now=NOW) is True
    # flip the box to aligned -> no drift
    (epic_dir / "e.json").write_text(json.dumps({
        "id": "e", "status": "open",
        "acceptance_criteria_status": ["[x] AC1 x"]}))
    assert rec.has_unresolved_drift(str(tmp_path), now=NOW) is False


def test_drift_summary_counts():
    epic = _epic(["[ ] AC1 a", "[x] AC2 b", "[x] AC3 c"])
    lugs = [
        _lug("l1", ["AC1"], [_green("AC1")]),                                  # under_report
        # AC2 box [x], no lug -> over_report
        _lug("l3", [{"ac": "AC3", "coverage": "partial", "pending": "x"}], [_green("AC3")]),  # mis_partial
    ]
    summary = rec.drift_summary(rec.reconcile_acs(epic, lugs, now=NOW))
    assert summary["under_report"] == 1
    assert summary["over_report"] == 1
    assert summary["mis_partial"] == 1
    assert summary["total_drift"] == 3
