#!/usr/bin/env python3
"""Acceptance-proof tests for impl-savepoint-loss-safety-net-v1 (test-at-birth).

Covers the two gaps the lug closes:
  AC1 — auto_eject_savepoint.py: a durable savepoint EXISTS on session end with
        unfinished work + none yet written; idempotent; clean session writes none;
        works in BOTH v3 and v4 layouts (mode-aware path resolution).
  AC2 — check_lug_no_resume_state.py: rejects a lug carrying resume-state fields,
        passes a clean lug.
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


AE = _load("auto_eject_savepoint")
LINT = _load("check_lug_no_resume_state")


# ---- layout helpers ---------------------------------------------------------

def _make_tree(tmp_path, mode):
    """Create a v3 or v4 working tree under tmp_path. Returns (root, base)."""
    root = str(tmp_path)
    if mode == "v4":
        base = os.path.join(root, "WAI-Harness", "spoke", "local")
    else:
        base = os.path.join(root, "WAI-Spoke")
    for sub in ("savepoints", "sessions", os.path.join("lugs", "bytype", "impl", "in_progress")):
        os.makedirs(os.path.join(base, sub), exist_ok=True)
    return root, base


def _write_state(base, rec):
    json.dump({"_session_state": {"next_session_recommendation": rec}},
              open(os.path.join(base, "WAI-State.json"), "w"))


def _add_in_progress_lug(base, lug_id):
    p = os.path.join(base, "lugs", "bytype", "impl", "in_progress", lug_id + ".json")
    json.dump({"id": lug_id, "status": "in_progress"}, open(p, "w"))


# ---- AC1: mode-aware resolution --------------------------------------------

def test_resolve_v3_layout(tmp_path):
    root, base = _make_tree(tmp_path, "v3")
    wb, mode = AE.resolve_working_base(root)
    assert mode == "v3"
    assert os.path.normpath(wb) == os.path.normpath(base)


def test_resolve_coexist_defaults_v3_overlap_safe(tmp_path):
    # Overlap safety (wai_paths): coexist with no explicit mode -> v3, so the
    # auto-eject savepoint lands where the still-v3 live resume path reads it.
    # v4 is an explicit opt-in (see test below / WAI_HARNESS_MODE=v4-only).
    root, base = _make_tree(tmp_path, "v3")
    _make_tree(tmp_path, "v4")  # add v4 too -> coexist
    wb, mode = AE.resolve_working_base(root)
    assert mode == "v3"
    assert os.path.normpath(wb) == os.path.normpath(base)


def test_resolve_v4_when_explicitly_requested(tmp_path):
    root, _ = _make_tree(tmp_path, "v3")
    _make_tree(tmp_path, "v4")
    wb, mode = AE.resolve_working_base(root, mode="v4-only")
    assert mode == "v4"
    assert wb.endswith(os.path.join("WAI-Harness", "spoke", "local"))


def test_resolve_v3_override_when_both_present(tmp_path):
    root, _ = _make_tree(tmp_path, "v3")
    _make_tree(tmp_path, "v4")
    wb, mode = AE.resolve_working_base(root, mode="v3")
    assert mode == "v3"


# ---- AC1: auto-eject fires / is idempotent / respects clean ----------------

def _fire(root, session, mode):
    return AE.run(session, root, mode=mode, dry_run=False)


def test_autoeject_writes_when_unfinished_v4(tmp_path):
    root, base = _make_tree(tmp_path, "v4")
    _write_state(base, "Resume Task 3: make wai-enter.sh harness-aware")
    _add_in_progress_lug(base, "impl-something-v1")
    res = _fire(root, "session-20260609-1605", "v4")
    assert res["action"] == "wrote"
    written = res["savepoint"]
    assert os.path.exists(written)
    sp = json.load(open(written))
    assert sp["status"] == "auto-eject" and sp["degraded"] is True
    assert sp["harness_mode"] == "v4"
    # first_actions[0] seeded from next_session_recommendation
    assert "wai-enter.sh" in sp["first_actions"][0]["action"]
    # in_progress lug captured + honest flag present
    assert "impl-something-v1" in sp["in_progress_lugs"]
    assert sp["honest_flags"] and "AUTO-GENERATED" in sp["honest_flags"][0]["flag"]


def test_autoeject_writes_when_unfinished_v3(tmp_path):
    root, base = _make_tree(tmp_path, "v3")
    _write_state(base, "")
    _add_in_progress_lug(base, "impl-v3-thing-v1")  # lug alone = unfinished
    res = _fire(root, "session-20260101-0000", "v3")
    assert res["action"] == "wrote"
    sp = json.load(open(res["savepoint"]))
    assert sp["harness_mode"] == "v3"
    # landed under the INITIATIVE-SCOPED home (no current.json pin -> unfiled bucket),
    # never the retired loose {base}/savepoints/ dir
    assert os.path.normpath(os.path.dirname(res["savepoint"])) == \
        os.path.normpath(os.path.join(base, "initiatives", "savepoints",
                                      "initiative-unfiled-savepoints-v1"))
    assert sp["initiative_id"] == "initiative-unfiled-savepoints-v1"


def test_autoeject_idempotent(tmp_path):
    root, base = _make_tree(tmp_path, "v4")
    _add_in_progress_lug(base, "impl-x-v1")
    first = _fire(root, "session-A", "v4")
    assert first["action"] == "wrote"
    second = _fire(root, "session-A", "v4")
    assert second["action"] == "skip"
    assert second["reason"] == "savepoint already exists for session"


def test_no_autoeject_when_clean(tmp_path):
    root, base = _make_tree(tmp_path, "v4")
    _write_state(base, "None")  # no rec, no in_progress lugs, no git repo
    res = _fire(root, "session-clean", "v4")
    assert res["action"] == "skip"
    assert res["reason"] == "no substantive unfinished work"
    assert not os.path.exists(os.path.join(base, "initiatives", "savepoints",
                              "initiative-unfiled-savepoints-v1", "sp-session-clean-autoeject.json"))
    assert not os.path.exists(os.path.join(base, "savepoints", "sp-session-clean-autoeject.json"))


def test_existing_savepoint_blocks_autoeject(tmp_path):
    root, base = _make_tree(tmp_path, "v4")
    _add_in_progress_lug(base, "impl-y-v1")
    # a real (authored) savepoint already claims this session
    json.dump({"id": "sp-real", "claiming_session_id": "session-Z"},
              open(os.path.join(base, "savepoints", "sp-real.json"), "w"))
    res = _fire(root, "session-Z", "v4")
    assert res["action"] == "skip" and res["savepoint"] == "sp-real.json"


# ---- AC2: side-channel lint -------------------------------------------------

def test_lint_rejects_lug_with_resume_state(tmp_path):
    p = os.path.join(str(tmp_path), "bad-lug.json")
    json.dump({"id": "lug-bad", "type": "task",
               "work_done": [{"what": "stuff"}],
               "savepoint_note": "resume here"}, open(p, "w"))
    banned = LINT.check_lug(p)
    assert "work_done" in banned and "savepoint_note" in banned


def test_lint_passes_clean_lug(tmp_path):
    p = os.path.join(str(tmp_path), "good-lug.json")
    json.dump({"id": "lug-good", "type": "impl", "status": "open",
               "tasks": ["do x"], "acceptance_criteria": []}, open(p, "w"))
    assert LINT.check_lug(p) == []
