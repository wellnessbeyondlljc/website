"""Acceptance proof: fleet_dashboard.py — registry-driven fleet christmas-tree (AC18).
Hermetic: synthetic registry + master + installs. Proves registry-sourced spoke list
(NOT fs-walk), _archive exclusion, per-spoke lights, and missing/no-v4 handling.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import manifest_build as mb  # noqa: E402
import fleet_dashboard as fd  # noqa: E402


def _master(tmp, files):
    m = tmp / "mywheel" / "WAI-Harness" / "spoke" / "managed"
    for r, c in files.items():
        (m / r).parent.mkdir(parents=True, exist_ok=True); (m / r).write_text(c)
    man = mb.build(str(m), str(m / mb.MANIFEST_NAME), now_iso="2026-01-01T00:00:00Z")
    (m / mb.MANIFEST_NAME).write_text(json.dumps(man, indent=2))
    return tmp / "mywheel" / "WAI-Harness"


def _install(root, files, current_manifest):
    m = root / "WAI-Harness" / "spoke" / "managed"
    for r, c in files.items():
        (m / r).parent.mkdir(parents=True, exist_ok=True); (m / r).write_text(c)
    (m / mb.MANIFEST_NAME).write_text(json.dumps(current_manifest, indent=2))


def test_dashboard_is_registry_driven_and_excludes_archive(tmp_path):
    files = {"a.py": "x\n"}
    master = _master(tmp_path, files)
    master_manifest = json.loads((master / "spoke/managed" / mb.MANIFEST_NAME).read_text())
    # registry: one good spoke, one archived (must be excluded), one missing-on-disk
    good = tmp_path / "good"; _install(good, files, master_manifest)
    (good / "WAI-Harness" / "spoke" / "local" / ".activated").parent.mkdir(parents=True, exist_ok=True)
    (good / "WAI-Harness" / "spoke" / "local" / ".activated").write_text("{}")
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps({"wheels": [
        {"wheel_id": "good", "path": str(good)},
        {"wheel_id": "legacy", "path": str(tmp_path / "_archive" / "old")},   # excluded
        {"wheel_id": "ghost", "path": str(tmp_path / "ghost")},               # missing on disk
    ]}))
    dash = fd.build_fleet_dashboard(str(reg), str(master), now_iso="2026-06-10T10:00:00Z")
    ids = [r["wheel_id"] for r in dash["rows"]]
    assert "legacy" not in ids                      # _archive excluded
    assert set(ids) == {"good", "ghost"}
    assert dash["summary"]["total"] == 2            # archive not counted
    good_row = next(r for r in dash["rows"] if r["wheel_id"] == "good")
    assert good_row["integrity"] == "PASS" and good_row["currency"] == "CURRENT"
    assert good_row["activation"] == "ACTIVE" and good_row["activation_ready"] is True
    ghost_row = next(r for r in dash["rows"] if r["wheel_id"] == "ghost")
    assert ghost_row["on_disk"] is False and ghost_row["has_v4"] is False


def test_pattern_monitor_reads_gate_log(tmp_path):
    files = {"a.py": "x\n"}
    master = _master(tmp_path, files)
    mm = json.loads((master / "spoke/managed" / mb.MANIFEST_NAME).read_text())
    sp = tmp_path / "s1"; _install(sp, files, mm)
    gl = sp / "WAI-Harness" / "spoke" / "managed" / "patterns" / "gate-log.jsonl"
    gl.parent.mkdir(parents=True, exist_ok=True)
    gl.write_text("\n".join(json.dumps(x) for x in [
        {"disposition": "approved"}, {"disposition": "approved"},
        {"disposition": "halted"}, {"disposition": "approved"}]) + "\n")
    reg = tmp_path / "r.json"; reg.write_text(json.dumps({"wheels": [{"wheel_id": "s1", "path": str(sp)}]}))
    dash = fd.build_fleet_dashboard(str(reg), str(master))
    pm = dash["rows"][0]["pattern"]
    assert pm["approval_rate"] == 0.75 and pm["open_halts"] == 1
