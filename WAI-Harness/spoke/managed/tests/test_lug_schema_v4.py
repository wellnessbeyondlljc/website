#!/usr/bin/env python3
"""Acceptance-proof tests for impl-lug-schema-v4-validator-v1 (test-at-birth).

Covers spec-lug-schema-v4-v1 + the impl lug's verification_test[]:
  vt-missing-rev, vt-rev-not-int, vt-bump-rev, vt-prepare-write-stale,
  vt-ac-uncovered, vt-context-fields, vt-v3-migrate-prompt, vt-dogfood-self.

Cross-checks that prepare_lug_write matches change_registry.check_rev semantics
(the LIVE consumer of the rev field).
"""
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(
        mod, os.path.join(ROOT, "tools", f"{mod}.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


V = _load("validate_lug_v4")
LU = _load("lug_utils")
CR = _load("change_registry")


def _valid_v4_lug(**over):
    lug = {
        "id": "impl-sample-v1",
        "type": "implementation",
        "status": "open",
        "schema_version": 4,
        "rev": 1,
        "title": "A sample v4 lug for validation tests",
        "impact": 7,
        "situation": "An observable condition that warranted this lug.",
        "decision_rationale": "Why this approach over alternatives, in full.",
        "alternatives_considered": ["X rejected because Y"],
        "context_snapshot": {"active_epics": ["epic-x"], "active_initiatives": []},
        "triggering_session": "session-20260609-0713",
        "acceptance_criteria": ["AC1 does the thing", "AC2 does the other thing"],
        "verification_test": [
            {"test_id": "t1", "covers_ac": "AC1: thing", "mode": "mechanical",
             "result": None, "check_ref": None},
            {"test_id": "t2", "covers_ac": "AC2: other", "mode": "mechanical",
             "result": 1, "check_ref": None},
        ],
        "bolt_ref": None,
    }
    lug.update(over)
    return lug


def test_valid_v4_passes():
    r = V.validate_lug_v4(_valid_v4_lug())
    assert r["ok"], r["failures"]
    assert not r["migrate_prompt"]


def test_missing_rev_fails():
    lug = _valid_v4_lug()
    del lug["rev"]
    r = V.validate_lug_v4(lug)
    assert not r["ok"]
    assert any("rev required" in f for f in r["failures"])


def test_rev_must_be_int():
    r = V.validate_lug_v4(_valid_v4_lug(rev="2"))
    assert not r["ok"]
    assert any("rev must be an integer" in f for f in r["failures"])
    # bool is not a valid rev (bool is an int subclass — must be rejected)
    r2 = V.validate_lug_v4(_valid_v4_lug(rev=True))
    assert not r2["ok"]


def test_bump_rev():
    lug = {"rev": 3}
    LU.bump_rev(lug, now_iso="2026-06-09T00:00:00Z")
    assert lug["rev"] == 4
    assert lug["updated_at"] == "2026-06-09T00:00:00Z"
    # absent rev initializes to 1
    fresh = {}
    LU.bump_rev(fresh, now_iso="2026-06-09T00:00:00Z")
    assert fresh["rev"] == 1


def test_prepare_write_concurrency():
    # stale write rejected
    r = LU.prepare_lug_write({"rev": 4}, write_against_rev=3)
    assert not r["ok"] and r.get("stale")
    # up-to-date write accepted, rev bumped
    lug = {"rev": 4}
    r2 = LU.prepare_lug_write(lug, write_against_rev=4, now_iso="2026-06-09T00:00:00Z")
    assert r2["ok"] and r2["next_rev"] == 5 and lug["rev"] == 5
    # missing rev banned
    r3 = LU.prepare_lug_write({}, write_against_rev=1)
    assert not r3["ok"] and "missing rev" in r3["reason"]


def test_prepare_write_matches_check_rev():
    """prepare_lug_write must agree with the LIVE consumer change_registry.check_rev."""
    # stale
    assert CR.check_rev(4, 3)["ok"] is False
    assert LU.prepare_lug_write({"rev": 4}, 3)["ok"] is False
    # fresh
    assert CR.check_rev(4, 4)["ok"] is True
    assert LU.prepare_lug_write({"rev": 4}, 4)["ok"] is True
    # missing
    assert CR.check_rev(None, 1)["ok"] is False
    assert LU.prepare_lug_write({}, 1)["ok"] is False


def test_ac_traceability():
    lug = _valid_v4_lug(acceptance_criteria=["AC1 a", "AC2 b", "AC3 c"])
    # only AC1, AC2 covered -> AC3 uncovered -> fail
    r = V.validate_lug_v4(lug)
    assert not r["ok"]
    assert any("AC3" in f for f in r["failures"])
    # cover AC3 -> pass
    lug["verification_test"].append(
        {"test_id": "t3", "covers_ac": "AC3: c", "mode": "mechanical", "result": None, "check_ref": None}
    )
    assert V.validate_lug_v4(lug)["ok"]


def test_mandatory_context():
    # missing situation fails
    lug = _valid_v4_lug()
    del lug["situation"]
    assert not V.validate_lug_v4(lug)["ok"]
    # high-impact lug missing alternatives_considered fails
    lug2 = _valid_v4_lug(impact=8)
    del lug2["alternatives_considered"]
    r = V.validate_lug_v4(lug2)
    assert not r["ok"]
    assert any("alternatives_considered" in f for f in r["failures"])
    # low-impact lug WITHOUT the rationale pair is fine
    lug3 = _valid_v4_lug(impact=3)
    del lug3["alternatives_considered"]
    del lug3["decision_rationale"]
    assert V.validate_lug_v4(lug3)["ok"]


def test_empty_verification_test_fails():
    assert not V.validate_lug_v4(_valid_v4_lug(verification_test=[]))["ok"]


def test_bad_mode_and_result():
    lug = _valid_v4_lug()
    lug["verification_test"][0]["mode"] = "vibes"
    lug["verification_test"][1]["result"] = 7
    r = V.validate_lug_v4(lug)
    assert not r["ok"]
    assert any("mode" in f for f in r["failures"])
    assert any("result" in f for f in r["failures"])


def test_v3_gets_migrate_prompt():
    r = V.validate_lug_v4({"id": "old", "type": "task", "title": "a v3 lug"})
    assert r["ok"] and r["migrate_prompt"]
    r2 = V.validate_lug_v4({"schema_version": 3, "id": "old"})
    assert r2["ok"] and r2["migrate_prompt"]


def test_this_lug_is_valid_v4():
    """Dogfood: the impl lug driving this work validates as a conformant v4 lug."""
    p = os.path.join(
        ROOT, "WAI-Spoke", "lugs", "bytype", "implementation", "in_progress",
        "impl-lug-schema-v4-validator-v1.json",
    )
    if not os.path.exists(p):
        # may already be completed
        p = os.path.join(
            ROOT, "WAI-Spoke", "lugs", "bytype", "implementation", "completed",
            "impl-lug-schema-v4-validator-v1.json",
        )
    lug = json.load(open(p))
    r = V.validate_lug_v4(lug)
    assert r["ok"], r["failures"]
