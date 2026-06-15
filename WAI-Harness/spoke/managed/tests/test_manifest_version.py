"""Acceptance proof: manifest_build.read_version — the harness version comes from a VERSION
file at the WAI-Harness root (bump it to evolve), not a hardcoded constant."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import manifest_build as mb  # noqa: E402


def test_reads_version_from_wai_harness_root(tmp_path):
    # layout: <root>/WAI-Harness/VERSION + .../spoke/managed
    wh = tmp_path / "WAI-Harness"
    managed = wh / "spoke" / "managed"
    managed.mkdir(parents=True)
    (wh / "VERSION").write_text("4.0.0-pre.7\n")
    assert mb.read_version(str(managed)) == "4.0.0-pre.7"


def test_fallback_when_no_version_file(tmp_path):
    managed = tmp_path / "WAI-Harness" / "spoke" / "managed"
    managed.mkdir(parents=True)
    assert mb.read_version(str(managed), fallback="X") == "X"


def test_build_stamps_version_from_file(tmp_path):
    wh = tmp_path / "WAI-Harness"
    managed = wh / "spoke" / "managed"
    managed.mkdir(parents=True)
    (managed / "a.py").write_text("x\n")
    (wh / "VERSION").write_text("4.0.0-pre.9")
    m = mb.build(str(managed), str(managed / mb.MANIFEST_NAME),
                 harness_version=mb.read_version(str(managed)), now_iso="2026-01-01T00:00:00Z")
    assert m["harness_version"] == "4.0.0-pre.9"
