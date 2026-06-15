#!/usr/bin/env python3
"""Acceptance-proof tests for impl-savepoint-resume-contract-skill-v1 (test-at-birth).

Covers spec-savepoint-resume-contract-v1 + the impl lug's verification_test[]:
  vt-thin-rejected, vt-deferred-capture, vt-handoff-fallback,
  vt-honest-flag-linkage, vt-nonempty-paper-trail, vt-no-60-cap,
  vt-handfeed-regression (structural proxy).

The gate under test is the deterministic tools/validate_savepoint.py
(spec-ceremony-lean-v1: the mechanical half of the resume-contract gate).
"""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(
        mod, os.path.join(ROOT, "tools", f"{mod}.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


VS = _load("validate_savepoint")


def _complete_savepoint():
    """A contract-complete savepoint (the reconstructed S45 scenario). where_captured
    points at a lug that exists in this repo so resolve_capture passes."""
    return {
        "id": "sp-test-complete",
        "work_done": [
            {"what": "Authored 3 phase-3 specs", "evidence": "commit f780b3f4", "verified": True},
        ],
        "where_we_are": "Harness v4; phases 0-2 done, phase-3 4-of-6. Next arc: phase 4 then 5.",
        "first_actions": [
            {"order": 1,
             "action": "Build the savepoint resume-contract validator and wire it into wai-savepoint",
             "command_or_target": "tools/validate_savepoint.py", "depends_on": None},
        ],
        "pending_handoffs": [
            {"id": "ecc", "what": "ECC stale-template fix", "to_whom": "Basher",
             "how_to_verify": "grep _detect_correction in .claude/hooks/synthesize_turn.py",
             "fallback_if_not_done": "git checkout HEAD -- .claude/hooks/synthesize_turn.py; nudge Basher",
             "lug_ref": "change-basher-synthesize-turn-ecc-stale-template-v1"},
        ],
        "deferred": [
            {"item": "mywheel registry + cutover", "why_deferred": "phase-5; blocked on green cert",
             "blocked_on": "green certification",
             "where_captured": "spec-savepoint-resume-contract-v1", "human_gate": True},
        ],
        "honest_flags": [
            {"flag": "verification-spine tests self-reviewed",
             "why_it_matters": "second-party QA review owed", "where_recorded": None},
        ],
        "blockers_and_human_gates": [],
        "open_questions": [],
        "workspace": {"path": "/home/mario/projects/wheelwright/framework",
                      "why": "framework is the live tested spoke; mywheel is not a git repo yet (phase-5 cutover)"},
        "inbox_snapshot": [],
        "paper_trail": {
            "lugs_completed": ["impl-savepoint-resume-contract-skill-v1"],
            "lugs_opened": [],
            "lugs_in_flight": [],
            "topics": ["savepoint resume contract"],
            "decisions": ["savepoint is a resume contract not a summary"],
        },
    }


def test_complete_savepoint_passes():
    r = VS.validate_resume_contract(_complete_savepoint(), spoke_root=ROOT)
    assert r["ok"], r["failures"]


def test_thin_savepoint_rejected():
    """vt-thin-rejected: a one-line work_done + empty first_actions fails."""
    sp = {"work_done": "did some stuff", "first_actions": [], "paper_trail": {}}
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert not r["ok"]
    assert any("first_actions empty" in f for f in r["failures"])
    assert any("work_done" in f for f in r["failures"])


def test_deferred_requires_capture():
    """vt-deferred-capture: a non-resolving where_captured fails; a real one passes."""
    sp = _complete_savepoint()
    sp["deferred"][0]["where_captured"] = "lug-does-not-exist-anywhere-v9"
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert not r["ok"]
    assert any("does not resolve" in f for f in r["failures"])

    sp["deferred"][0]["where_captured"] = "spec-capabilitiesgraph-v1"  # exists in repo
    assert VS.validate_resume_contract(sp, spoke_root=ROOT)["ok"]


def test_deferred_missing_capture():
    sp = _complete_savepoint()
    del sp["deferred"][0]["where_captured"]
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert not r["ok"]
    assert any("LOST item" in f for f in r["failures"])


def test_handoff_needs_fallback():
    """vt-handoff-fallback: a handoff missing fallback_if_not_done fails."""
    sp = _complete_savepoint()
    del sp["pending_handoffs"][0]["fallback_if_not_done"]
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert not r["ok"]
    assert any("fallback_if_not_done" in f for f in r["failures"])


def test_handoff_needs_verify():
    sp = _complete_savepoint()
    del sp["pending_handoffs"][0]["how_to_verify"]
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert not r["ok"]
    assert any("how_to_verify" in f for f in r["failures"])


def test_unverified_needs_flag():
    """vt-honest-flag-linkage: a verified=false item with no honest_flag fails."""
    sp = _complete_savepoint()
    sp["work_done"].append({"what": "edited a thing", "evidence": "?", "verified": False})
    sp["honest_flags"] = []
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert not r["ok"]
    assert any("probably done" in f for f in r["failures"])

    # with a matching honest_flag it passes
    sp["honest_flags"] = [{"flag": "edit unverified", "why_it_matters": "x", "where_recorded": None}]
    assert VS.validate_resume_contract(sp, spoke_root=ROOT)["ok"]


def test_paper_trail_nonempty():
    """vt-nonempty-paper-trail: topics=[] for a lug-touching session fails."""
    sp = _complete_savepoint()
    sp["paper_trail"]["topics"] = []
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert not r["ok"]
    assert any("topics empty" in f for f in r["failures"])


def test_paper_trail_empty_session_ok():
    """A session that touched NO lugs is not forced to have topics/decisions."""
    sp = _complete_savepoint()
    sp["paper_trail"] = {"lugs_completed": [], "lugs_opened": [], "lugs_in_flight": [],
                         "topics": [], "decisions": []}
    assert VS.validate_resume_contract(sp, spoke_root=ROOT)["ok"]


def test_no_resume_char_cap():
    """vt-no-60-cap: a 200-char first action is accepted (v3 cap removed)."""
    sp = _complete_savepoint()
    sp["first_actions"][0]["action"] = "x" * 200
    assert VS.validate_resume_contract(sp, spoke_root=ROOT)["ok"]


def test_handfeed_regression_structural():
    """vt-handfeed-regression (structural proxy): the reconstructed S45 contract-complete
    savepoint carries both confirms, the deferred item, and the honest flag — so a fresh
    agent has every input the user had to hand-feed. The attested end-to-end (a subagent
    asking zero questions) is recorded in the impl lug as an attested-tier check."""
    sp = _complete_savepoint()
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert r["ok"], r["failures"]
    assert sp["pending_handoffs"], "S45 needed the pending handoff present"
    assert sp["deferred"], "S45 needed the deferred item present"
    assert sp["honest_flags"], "S45 needed the self-reviewed-tests honest flag present"


def test_missing_workspace_fails():
    """Hardened S45: a savepoint must say WHERE to work (framework vs mywheel)."""
    sp = _complete_savepoint()
    del sp["workspace"]
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert not r["ok"]
    assert any("workspace missing" in f for f in r["failures"])


def test_decision_fork_in_first_action_warns():
    """first_actions[0] must be DECIDED, not a fork — warned, not failed."""
    sp = _complete_savepoint()
    sp["first_actions"][0]["action"] = "Pick the hub Postgres tier OR the dashboard, then build it"
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert r["ok"], "a fork warns but does not block"
    assert any("decision/fork" in w for w in r["warnings"])


def test_missing_inbox_snapshot_warns():
    sp = _complete_savepoint()
    del sp["inbox_snapshot"]
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert r["ok"]
    assert any("inbox_snapshot" in w for w in r["warnings"])


def test_decided_first_action_no_warning():
    sp = _complete_savepoint()
    sp["first_actions"][0]["action"] = "Build tools/reconcile_epic_acs.py per its lug, test-at-birth"
    r = VS.validate_resume_contract(sp, spoke_root=ROOT)
    assert not any("decision/fork" in w for w in r["warnings"])


def test_resolve_capture_path_and_lug():
    assert VS.resolve_capture("spec-lug-schema-v4-v1", spoke_root=ROOT)
    assert VS.resolve_capture("CLAUDE.md", spoke_root=ROOT)
    assert not VS.resolve_capture("totally-made-up-id-zzz", spoke_root=ROOT)
    assert not VS.resolve_capture("", spoke_root=ROOT)


def test_resolve_capture_v4_only_isolates_to_v4_tree(tmp_path, monkeypatch):
    """V4-COMPLETE Phase B: under WAI_HARNESS_MODE=v4-only, lug discovery reads the
    v4 tree and NEVER the legacy WAI-Spoke tree; coexist falls back to v3."""
    d = str(tmp_path)
    v4lugs = tmp_path / "WAI-Harness" / "spoke" / "local" / "lugs" / "bytype" / "task" / "open"
    v3lugs = tmp_path / "WAI-Spoke" / "lugs" / "bytype" / "task" / "open"
    v4lugs.mkdir(parents=True)
    v3lugs.mkdir(parents=True)
    (v4lugs / "task-foo-v1.json").write_text("{}")
    (v3lugs / "task-bar-v1.json").write_text("{}")  # exists ONLY in v3

    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    assert VS.resolve_capture("task-foo-v1", spoke_root=d) is True
    assert VS.resolve_capture("task-bar-v1", spoke_root=d) is False  # zero WAI-Spoke access

    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
    assert VS.resolve_capture("task-bar-v1", spoke_root=d) is True  # coexist fallback
