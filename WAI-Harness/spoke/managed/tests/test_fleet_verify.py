"""Acceptance proof: fleet_verify + harness_activate parity gate
(task-fleet-recurrency-before-activation-v1 AC1 + AC3).

Builds a synthetic master wheel + spoke installs on a tmp tree and proves the
three fleet-verify dimensions and the activation parity gate behave exactly as
the fleet-verification contract requires. No network, no real fleet — hermetic.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import manifest_build  # noqa: E402
import fleet_verify  # noqa: E402
import harness_activate  # noqa: E402


def _write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _make_install(install: Path, files: dict, build_own_manifest=True):
    """Create a WAI-Harness install with spoke/managed/<files>. Optionally stamp
    its OWN MANIFEST so integrity verifies against on-disk content."""
    managed = install / "spoke" / "managed"
    for rel, content in files.items():
        _write(managed / rel, content)
    if build_own_manifest:
        manifest_build.build(str(managed), str(managed / "MANIFEST.json"),
                             now_iso="2026-01-01T00:00:00Z")
    return install


def _master(tmp_path: Path, files: dict) -> Path:
    master = tmp_path / "mywheel" / "WAI-Harness"
    _make_install(master, files)
    return master


# ============ fleet_verify: parity (compare_to_master) ============

def test_current_spoke_matches_master(tmp_path):
    files = {"a.py": "print(1)\n", "skills/b.md": "# b\n"}
    master = _master(tmp_path, files)
    master_files = fleet_verify.load_manifest_files(master / fleet_verify.MANIFEST_REL)
    install = _make_install(tmp_path / "spoke1" / "WAI-Harness", files)
    parity = fleet_verify.compare_to_master(install / fleet_verify.MANAGED_REL, master_files)
    assert parity["current"] is True
    assert parity["missing"] == [] and parity["stale"] == []


def test_missing_file_is_stale(tmp_path):
    master = _master(tmp_path, {"a.py": "x\n", "b.py": "y\n"})
    master_files = fleet_verify.load_manifest_files(master / fleet_verify.MANIFEST_REL)
    install = _make_install(tmp_path / "spoke1" / "WAI-Harness", {"a.py": "x\n"})
    parity = fleet_verify.compare_to_master(install / fleet_verify.MANAGED_REL, master_files)
    assert parity["current"] is False
    assert parity["missing"] == ["b.py"]


def test_changed_hash_is_stale(tmp_path):
    master = _master(tmp_path, {"a.py": "MASTER\n"})
    master_files = fleet_verify.load_manifest_files(master / fleet_verify.MANIFEST_REL)
    install = _make_install(tmp_path / "spoke1" / "WAI-Harness", {"a.py": "OLD\n"})
    parity = fleet_verify.compare_to_master(install / fleet_verify.MANAGED_REL, master_files)
    assert parity["current"] is False
    assert parity["stale"] == ["a.py"]


def test_extra_file_does_not_block_currency(tmp_path):
    master = _master(tmp_path, {"a.py": "x\n"})
    master_files = fleet_verify.load_manifest_files(master / fleet_verify.MANIFEST_REL)
    install = _make_install(tmp_path / "spoke1" / "WAI-Harness",
                            {"a.py": "x\n", "extra.py": "local\n"})
    parity = fleet_verify.compare_to_master(install / fleet_verify.MANAGED_REL, master_files)
    assert parity["current"] is True
    assert parity["extra"] == ["extra.py"]


# ============ fleet_verify: integrity ============

def test_integrity_fail_on_tampered_managed_file(tmp_path):
    master = _master(tmp_path, {"a.py": "x\n"})
    master_files = fleet_verify.load_manifest_files(master / fleet_verify.MANIFEST_REL)
    install = _make_install(tmp_path / "spoke1" / "WAI-Harness", {"a.py": "x\n"})
    (install / fleet_verify.MANAGED_REL / "a.py").write_text("TAMPERED\n")  # after manifest stamp
    verdict = fleet_verify.classify_install(install, master_files)
    assert verdict["integrity"] == "FAIL"
    assert verdict["activation_ready"] is False


# ============ fleet_verify: discovery + run ============

def test_find_installs_excludes_master_and_trash(tmp_path):
    master = _master(tmp_path, {"a.py": "x\n"})
    _make_install(tmp_path / "spoke1" / "WAI-Harness", {"a.py": "x\n"})
    _make_install(tmp_path / "trash_bin" / "old" / "WAI-Harness", {"a.py": "x\n"})
    installs = fleet_verify.find_installs(tmp_path, master)
    names = [str(p) for p in installs]
    assert any("spoke1" in n for n in names)
    assert not any("trash_bin" in n for n in names)
    assert str(master) not in names


def test_run_report_shape_and_counts(tmp_path):
    files = {"a.py": "x\n"}
    master = _master(tmp_path, files)
    _make_install(tmp_path / "current" / "WAI-Harness", files)               # CURRENT
    _make_install(tmp_path / "stale" / "WAI-Harness", {"a.py": "OLD\n"})      # STALE
    report = fleet_verify.run(tmp_path, master, now_iso="2026-06-10T00:00:00Z")
    assert report["summary"]["installs"] == 2
    assert report["summary"]["integrity_pass"] == 2
    assert report["summary"]["currency_current"] == 1
    assert report["summary"]["activation_active"] == 0
    assert report["summary"]["activation_ready"] == 1


# ============ harness_activate: canonical lifecycle ============

def _spoke_root_with_v4(tmp_path, managed_files, *, v3=True):
    """A spoke_root holding WAI-Harness/ (v4 install) and optionally WAI-Spoke/ (v3)."""
    root = tmp_path / "spokeA"
    _make_install(root / "WAI-Harness", managed_files)
    if v3:
        _write(root / "WAI-Spoke" / "WAI-State.json", json.dumps({"v": 3}))
        _write(root / "WAI-Spoke" / "sessions" / "s1" / "track.jsonl", "{}\n")
    return root


def test_status_dormant_until_activate_marker(tmp_path):
    root = _spoke_root_with_v4(tmp_path, {"a.py": "x\n"})
    assert harness_activate.status(root) == "upgraded_dormant"
    (root / "WAI-Harness" / harness_activate.ACTIVATE_MARKER).write_text("")
    assert harness_activate.status(root) == "activation_requested"


def test_dormant_activate_is_noop(tmp_path):
    root = _spoke_root_with_v4(tmp_path, {"a.py": "x\n"})
    res = harness_activate.activate(root, dry_run=False, master_dir=None)
    assert res["action"] == "none"
    assert not (root / "WAI-Harness" / harness_activate.ACTIVATED_MARKER).exists()


# ============ harness_activate: parity GATE (AC1) ============

def test_activation_blocked_on_stale_snapshot(tmp_path):
    master = _master(tmp_path, {"a.py": "MASTER\n", "b.py": "y\n"})
    root = _spoke_root_with_v4(tmp_path, {"a.py": "OLD\n"})  # stale + missing b.py
    (root / "WAI-Harness" / harness_activate.ACTIVATE_MARKER).write_text("")
    res = harness_activate.activate(root, dry_run=False, master_dir=master)
    assert res["action"] == "blocked" and res["blocked"] is True
    assert res["blockers"]
    # gate's whole purpose: marker NOT written, so still not activated
    assert not (root / "WAI-Harness" / harness_activate.ACTIVATED_MARKER).exists()
    assert harness_activate.status(root) == "activation_requested"


def test_activation_succeeds_when_current(tmp_path):
    files = {"a.py": "x\n", "b.py": "y\n"}
    master = _master(tmp_path, files)
    root = _spoke_root_with_v4(tmp_path, files)
    (root / "WAI-Harness" / harness_activate.ACTIVATE_MARKER).write_text("")
    res = harness_activate.activate(root, dry_run=False, master_dir=master)
    assert res["action"].startswith("migrate") and not res.get("blocked")
    marker = root / "WAI-Harness" / harness_activate.ACTIVATED_MARKER
    assert marker.exists()
    data = json.loads(marker.read_text())
    assert data["parity"] == "current" and data["forced"] is False
    assert harness_activate.status(root) == "activated"
    # migration COPIED v3 state into v4 local/ (non-destructive: v3 still present)
    assert (root / "WAI-Harness" / "spoke" / "local" / "WAI-State.json").exists()
    assert (root / "WAI-Spoke" / "WAI-State.json").exists()


def test_force_overrides_gate_but_records_forced(tmp_path):
    master = _master(tmp_path, {"a.py": "MASTER\n"})
    root = _spoke_root_with_v4(tmp_path, {"a.py": "OLD\n"})
    (root / "WAI-Harness" / harness_activate.ACTIVATE_MARKER).write_text("")
    res = harness_activate.activate(root, dry_run=False, master_dir=master, force=True)
    assert res.get("forced") is True and not res.get("blocked")
    data = json.loads((root / "WAI-Harness" / harness_activate.ACTIVATED_MARKER).read_text())
    assert data["forced"] is True and data["parity"] == "FORCED-STALE"


def test_already_activated_is_idempotent(tmp_path):
    files = {"a.py": "x\n"}
    master = _master(tmp_path, files)
    root = _spoke_root_with_v4(tmp_path, files)
    (root / "WAI-Harness" / harness_activate.ACTIVATE_MARKER).write_text("")
    harness_activate.activate(root, dry_run=False, master_dir=master)
    res2 = harness_activate.activate(root, dry_run=False, master_dir=master)
    assert res2["action"] == "none" and "idempotent" in res2["note"]


def test_parity_blockers_clear_for_current(tmp_path):
    files = {"a.py": "x\n"}
    master = _master(tmp_path, files)
    root = _spoke_root_with_v4(tmp_path, files)
    assert harness_activate.parity_blockers(root, master) == []


# ============ manifest_build: never distribute bytecode/cache cruft ============

def test_manifest_excludes_pycache_and_pyc(tmp_path):
    managed = tmp_path / "managed"
    _write(managed / "real.py", "print(1)\n")
    _write(managed / "__pycache__" / "real.cpython-312.pyc", "BYTECODE")
    _write(managed / ".pytest_cache" / "v" / "lastfailed", "{}")
    _write(managed / "sub" / "ok.md", "# ok\n")
    _write(managed / "sub" / ".DS_Store", "junk")
    m = manifest_build.build(str(managed), str(managed / "MANIFEST.json"),
                             now_iso="2026-01-01T00:00:00Z")
    keys = set(m["files"])
    assert "real.py" in keys and os.path.join("sub", "ok.md") in keys
    assert not any("__pycache__" in k or k.endswith(".pyc") or ".pytest_cache" in k
                   or k.endswith(".DS_Store") for k in keys)
    # and verify is stable (no 'new' churn from regenerated bytecode)
    res = manifest_build.verify(str(managed), str(managed / "MANIFEST.json"))
    assert res["ok"] and res["new"] == []
