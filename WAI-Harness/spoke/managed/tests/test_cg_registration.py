"""Acceptance proof: audit_cg_registration.py — CG command-registration completeness (AC16).
Hermetic: synthetic command dir + synthetic CG entries.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import audit_cg_registration as acr  # noqa: E402


def _mk(spoke, names):
    d = spoke / "templates" / "commands"
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_text("# " + n + "\n")
    return spoke


def test_all_registered_is_clean(tmp_path):
    _mk(tmp_path, ["wai.md", "wai-closeout.md", "wai-status.md"])
    cg = [{"file_paths": ["templates/commands/" + n]} for n in
          ("wai.md", "wai-closeout.md", "wai-status.md")]
    disc = acr.discover_commands(tmp_path)
    rep = acr.audit_registration(disc, cg)
    assert rep["ok"] is True and rep["unregistered"] == [] and rep["coverage_pct"] == 100.0


def test_unregistered_are_flagged_as_gaps(tmp_path):
    _mk(tmp_path, ["wai.md", "wai-closeout.md", "secret-cmd.md", "another.md"])
    cg = [{"file_paths": ["templates/commands/wai.md"]},
          {"file_paths": ["templates/commands/wai-closeout.md"]}]
    disc = acr.discover_commands(tmp_path)
    rep = acr.audit_registration(disc, cg)
    assert rep["ok"] is False
    assert sorted(u.split("/")[-1] for u in rep["unregistered"]) == ["another.md", "secret-cmd.md"]
    assert len(rep["gaps"]) == 2 and all(g["gap_type"] == acr.GAP_TYPE for g in rep["gaps"])
    assert rep["registered"] == 2 and rep["total_commands"] == 4


def test_declined_command_not_a_gap(tmp_path):
    _mk(tmp_path, ["wai.md", "internal-helper.md"])
    cg = [{"file_paths": ["templates/commands/wai.md"]}]
    disc = acr.discover_commands(tmp_path)
    rep = acr.audit_registration(disc, cg, declined={"internal-helper.md"})
    assert rep["ok"] is True and rep["unregistered"] == [] and "internal-helper.md" in rep["declined"]


def test_discover_handles_missing_dirs(tmp_path):
    # no templates/commands dir at all -> empty discovery, no crash
    disc = acr.discover_commands(tmp_path)
    assert disc == {}
    rep = acr.audit_registration(disc, [])
    assert rep["ok"] is True and rep["coverage_pct"] == 100.0
