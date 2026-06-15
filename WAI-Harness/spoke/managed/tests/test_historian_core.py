#!/usr/bin/env python3
"""Verification test for impl-historian-core-survey-v1 (test-at-birth).

Covers verify[]: enumeration + per-entry classification, self-reported coverage
(unscanned never silently dropped), bucket-suggestion heuristics, git_tracked
on/off repo, typed gaps (decision-undocumented / cruft), and that write_survey
satisfies v4_migrate's survey precondition.
"""
import importlib.util
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


HC = _load("historian_core")
MG = _load("v4_migrate")


def test_survey_enumerates_and_reports_full_coverage():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "lugs"))
        open(os.path.join(d, "lugs", "a.json"), "w").write("{}")
        open(os.path.join(d, "WAI-State.json"), "w").write("{}")
        rep = HC.survey(d, now_iso="2026-06-09T00:00:00Z")
        names = {e["name"] for e in rep["entries"]}
        assert names == {"lugs", "WAI-State.json"}
        assert rep["coverage_pct"] == 1.0 and rep["unscanned"] == []
        # assets_by_kind counts sum to scanned count
        assert sum(rep["assets_by_kind"].values()) == len(rep["scanned"])
        # WAI-State.json classified as state
        st = [e for e in rep["entries"] if e["name"] == "WAI-State.json"][0]
        assert st["kind"] == "state"


def test_suggest_bucket_heuristics():
    assert HC.suggest_bucket(".autosave") == "Drop"
    assert HC.suggest_bucket("WAI-State.json.template") == "Flag"
    assert HC.suggest_bucket("WAI-LugIndex.jsonl") == "Transform"
    assert HC.suggest_bucket("lugs") == "Preserve"


def test_git_tracked_on_and_off_repo():
    # the real repo: tracked names include known files, no crash
    tracked = HC.git_tracked(ROOT)
    assert isinstance(tracked, set)
    # off-repo temp dir -> empty set, no crash
    with tempfile.TemporaryDirectory() as d:
        assert HC.git_tracked(d) == set()


def test_typed_gaps_untracked_and_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        # off-repo so everything is "untracked"
        open(os.path.join(d, "loose.txt"), "w").write("x")
        os.makedirs(os.path.join(d, "emptydir"))
        rep = HC.survey(d)
        gap_types = {g["gap"] for g in rep["gaps"]}
        assert "decision-undocumented" in gap_types, "untracked file flagged"
        assert "cruft/misplacement" in gap_types, "empty dir flagged"


def test_unscanned_is_explicit_not_silent():
    # a survey of a non-existent root reports the gap, never a false 'complete'
    rep = HC.survey("/nonexistent/path/xyzzy")
    assert rep["coverage_pct"] == 0.0 and rep["unscanned"], "missing root surfaced, not silent"


def test_write_survey_satisfies_migration_precondition():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "lugs"))
        rep = HC.survey(d, now_iso="2026-06-09T00:00:00Z")
        assert MG.has_current_survey(d) is False  # not yet written
        HC.write_survey(rep, os.path.join(d, HC.SURVEY_NAME))
        assert MG.has_current_survey(d) is True, "written survey satisfies v4_migrate precondition"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASS")
