#!/usr/bin/env python3
"""Test-at-birth for the v4 lug creation stamper (tools/new_lug.py, AC10/AC11).

Verifies the creation-time half of the dual gate: auto-stamps schema_version/rev/
context_snapshot/triggering_session so they can't be forgotten, and refuses to
write a lug missing a mandatory content field (title, situation).
"""
import importlib.util
import json
import os
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(
        mod, os.path.join(ROOT, "tools", f"{mod}.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


NL = _load("new_lug")


def _spoke(d):
    spoke = Path(d) / "WAI-Spoke"
    (spoke / "runtime").mkdir(parents=True)
    (spoke / "lugs" / "bytype" / "epic" / "open").mkdir(parents=True)
    (spoke / "lugs" / "bytype" / "epic" / "in_progress").mkdir(parents=True)
    (spoke / "runtime" / "session-guard.json").write_text(
        json.dumps({"session_id": "session-20260609-test"})
    )
    (spoke / "WAI-State.json").write_text(json.dumps({
        "_active_initiative": "init-x",
        "_strategic_initiatives": [{"id": "init-y"}],
    }))
    (spoke / "lugs" / "bytype" / "epic" / "open" / "epic-foo-v1.json").write_text("{}")
    return str(Path(d))


def test_auto_stamps_v4_fields():
    with tempfile.TemporaryDirectory() as d:
        root = _spoke(d)
        lug = NL.build_v4_lug("impl-x-v1", "implementation", "A real title for the lug",
                              spoke_path=root, situation="closeout halted 3x on step X")
        assert lug["schema_version"] == 4
        assert lug["rev"] == 1
        assert lug["status"] == "draft"
        assert lug["created_at"] and lug["updated_at"]
        assert lug["triggering_session"] == "session-20260609-test"
        assert "epic-foo-v1" in lug["context_snapshot"]["active_epics"]
        assert "init-x" in lug["context_snapshot"]["active_initiatives"]
        assert "init-y" in lug["context_snapshot"]["active_initiatives"]


def test_strategic_initiatives_config_dict_not_polluted():
    """Regression (dogfood-caught S45): _strategic_initiatives is a CONFIG dict in real
    spokes — its keys must NOT leak into active_initiatives."""
    with tempfile.TemporaryDirectory() as d:
        spoke = Path(d) / "WAI-Spoke"
        (spoke / "runtime").mkdir(parents=True)
        (spoke / "lugs" / "bytype" / "epic" / "open").mkdir(parents=True)
        (spoke / "WAI-State.json").write_text(json.dumps({
            "_active_initiative": "init-real",
            "_strategic_initiatives": {"index_path": "x", "theme_count": 7,
                                       "initiative_count": 6, "scoring_cadence": "monthly"},
        }))
        snap = NL.resolve_context_snapshot(str(Path(d)))
        assert snap["active_initiatives"] == ["init-real"], snap
        assert "index_path" not in snap["active_initiatives"]
        assert "theme_count" not in snap["active_initiatives"]


def test_refuses_missing_situation():
    with tempfile.TemporaryDirectory() as d:
        root = _spoke(d)
        try:
            NL.build_v4_lug("impl-x-v1", "implementation", "title", spoke_path=root)
            assert False, "should have refused: missing situation"
        except ValueError as e:
            assert "situation" in str(e)


def test_refuses_missing_title():
    with tempfile.TemporaryDirectory() as d:
        root = _spoke(d)
        try:
            NL.build_v4_lug("impl-x-v1", "implementation", "", spoke_path=root,
                            situation="s")
            assert False, "should have refused: missing title"
        except ValueError as e:
            assert "title" in str(e)


def test_writes_to_draft_and_validates_structure():
    """The stamped draft carries every AUTO field validate_lug_v4 checks for presence."""
    with tempfile.TemporaryDirectory() as d:
        root = _spoke(d)
        lug = NL.build_v4_lug("impl-x-v1", "implementation", "A real title",
                              spoke_path=root, situation="observable condition",
                              impact=4)
        path = NL.write_lug(lug, root)
        assert path.endswith("bytype/implementation/draft/impl-x-v1.json")
        on_disk = json.loads(Path(path).read_text())
        # the structural fields validate_lug_v4 requires are all present
        for f in ("schema_version", "rev", "situation", "context_snapshot",
                  "triggering_session"):
            assert f in on_disk


def test_resolve_triggering_session_fallback():
    with tempfile.TemporaryDirectory() as d:
        spoke = Path(d) / "WAI-Spoke"
        spoke.mkdir(parents=True)
        # no guard, no state -> env or 'unknown'
        sid = NL.resolve_triggering_session(str(Path(d)))
        assert sid  # never empty
