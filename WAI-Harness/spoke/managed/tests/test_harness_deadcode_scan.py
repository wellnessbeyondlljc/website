"""Tests for harness_deadcode_scan: broken-ref detection is authoritative,
orphan detection is advisory, exit code gates on broken refs only."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import harness_deadcode_scan as hds  # noqa: E402


def _mk_spoke(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "templates" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "hooks").mkdir(parents=True)
    return tmp_path


def test_invoked_vs_orphan(tmp_path):
    sp = _mk_spoke(tmp_path)
    (sp / "tools" / "live_tool.py").write_text("print('hi')\n")
    (sp / "tools" / "dead_tool.py").write_text("print('bye')\n")
    # A skill invokes live_tool.py; dead_tool.py is named nowhere executable.
    (sp / "templates" / "commands" / "do.md").write_text("Run `python3 tools/live_tool.py` here.\n")
    out = hds.scan(sp, tmp_path / "no-basher")
    invoked = {t["tool"] for t in out["_full"]["INVOKED"]}
    orphaned = {o["tool"] for o in out["orphaned"]}
    assert "tools/live_tool.py" in invoked
    assert "tools/dead_tool.py" in orphaned


def test_broken_ref_detected(tmp_path):
    sp = _mk_spoke(tmp_path)
    (sp / "tools" / "real.py").write_text("x=1\n")
    (sp / "templates" / "commands" / "skill.md").write_text(
        "Calls `tools/real.py` and also `tools/ghost.py` which does not exist.\n")
    out = hds.scan(sp, tmp_path / "no-basher")
    missing = {b["missing_tool"] for b in out["broken_refs"]}
    assert "tools/ghost.py" in missing
    assert "tools/real.py" not in missing


def test_orphan_lists_mention_context(tmp_path):
    sp = _mk_spoke(tmp_path)
    (sp / "tools" / "spec_tool.py").write_text("x=1\n")
    (sp / "DESIGN.md").write_text("spec_tool is planned but unwired.\n")
    out = hds.scan(sp, tmp_path / "no-basher")
    orphan = next(o for o in out["orphaned"] if o["tool"] == "tools/spec_tool.py")
    assert "docs/specs" in orphan["mentions"]


def test_exit_gates_on_broken_only(tmp_path, monkeypatch):
    sp = _mk_spoke(tmp_path)
    (sp / "tools" / "orphan.py").write_text("x=1\n")  # orphan, no broken ref
    rc = hds._main(["--spoke-path", str(sp), "--basher", str(tmp_path / "nb")])
    assert rc == 0  # orphan candidates alone never fail the gate

    (sp / "templates" / "commands" / "s.md").write_text("`tools/missing.py`\n")
    rc2 = hds._main(["--spoke-path", str(sp), "--basher", str(tmp_path / "nb")])
    assert rc2 == 1  # a broken ref fails the gate
