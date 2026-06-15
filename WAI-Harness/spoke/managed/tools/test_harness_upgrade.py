"""Test-at-birth for harness_upgrade.py - the cutover-gating upgrade path.

Proves the verify-apply-verify loop for BOTH a spoke and the hub:
  - dry-run home-map classifies add/change/unchanged/orphan and writes nothing
  - apply brings the target's managed tree to match the master MANIFEST (verify-post ok)
  - the target's local/ tree is NEVER touched (the per-spoke guarantee)
  - verify catches a corrupted managed file (md5 mismatch)
  - the hub managed tree upgrades by the same engine
"""
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_upgrade as hu


def _write(p, text):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _make_master(root, files):
    managed = Path(root) / "managed"
    for rel, txt in files.items():
        _write(managed / rel, txt)
    m = hu.build_manifest(managed, generated_at="2026-01-01T00:00:00Z")
    (managed / hu.MANIFEST_NAME).write_text(json.dumps(m, indent=2) + "\n")
    return managed


def test_dry_run_home_map_writes_nothing(tmp_path):
    master = _make_master(tmp_path / "master",
                          {"tools/a.py": "v2\n", "skills/x.md": "new\n"})
    target = tmp_path / "target" / "managed"
    _write(target / "tools/a.py", "v1\n")           # CHANGE
    _write(target / "tools/old.py", "stale\n")      # ORPHAN
    before = (target / "tools/a.py").read_text()

    rep = hu.upgrade(master, target, dry_run=True)
    hm = rep["home_map"]
    assert "skills/x.md" in hm["add"]
    assert "tools/a.py" in hm["change"]
    assert "tools/old.py" in hm["orphan"]
    assert rep["applied"] == 0
    assert (target / "tools/a.py").read_text() == before   # untouched by dry-run
    assert not (target / "skills/x.md").exists()


def test_apply_brings_target_to_master_and_verifies(tmp_path):
    master = _make_master(tmp_path / "master",
                          {"tools/a.py": "v2\n", "skills/x.md": "new\n"})
    target = tmp_path / "target" / "managed"
    _write(target / "tools/a.py", "v1\n")

    rep = hu.upgrade(master, target, dry_run=False)
    assert rep["ok"] is True
    assert rep["verify_post"]["ok"] is True
    assert (target / "tools/a.py").read_text() == "v2\n"
    assert (target / "skills/x.md").read_text() == "new\n"
    # the target now carries the master manifest
    assert (target / hu.MANIFEST_NAME).exists()


def test_local_tree_never_touched(tmp_path):
    master = _make_master(tmp_path / "master", {"tools/a.py": "v2\n"})
    spoke = tmp_path / "target"
    target_managed = spoke / "managed"
    _write(target_managed / "tools/a.py", "v1\n")
    # a per-spoke local file + a session - must survive the upgrade verbatim
    _write(spoke / "local" / "sessions" / "s1" / "track.jsonl", '{"event":"turn"}\n')
    _write(spoke / "local" / "WAI-State.json", '{"mine":true}\n')

    hu.upgrade(master, target_managed, dry_run=False)

    assert (spoke / "local" / "sessions" / "s1" / "track.jsonl").read_text() == '{"event":"turn"}\n'
    assert (spoke / "local" / "WAI-State.json").read_text() == '{"mine":true}\n'


def test_verify_catches_corruption(tmp_path):
    master = _make_master(tmp_path / "master", {"tools/a.py": "v2\n"})
    target = tmp_path / "target" / "managed"
    hu.upgrade(master, target, dry_run=False)
    # corrupt a managed file post-upgrade
    (target / "tools/a.py").write_text("tampered\n")
    r = hu.verify(target, hu.load_manifest(master))
    assert r["ok"] is False
    assert any(m["file"] == "tools/a.py" for m in r["mismatches"])


def test_verify_catches_missing(tmp_path):
    master = _make_master(tmp_path / "master", {"tools/a.py": "v2\n", "tools/b.py": "x\n"})
    target = tmp_path / "target" / "managed"
    hu.upgrade(master, target, dry_run=False)
    (target / "tools/b.py").unlink()
    r = hu.verify(target, hu.load_manifest(master))
    assert r["ok"] is False
    assert "tools/b.py" in r["missing"]


def test_hub_upgrades_by_same_engine(tmp_path):
    # hub managed tree (capabilities-graph-hub.json) upgrades identically
    master = _make_master(tmp_path / "hubmaster",
                          {"capabilities-graph-hub.json": '{"entries":["v2"]}\n'})
    target = tmp_path / "hubtarget" / "managed"
    _write(target / "capabilities-graph-hub.json", '{"entries":["v1"]}\n')
    _write(tmp_path / "hubtarget" / "local" / "notes.json", '{"local":1}\n')

    rep = hu.upgrade(master, target, dry_run=False)
    assert rep["ok"] is True
    assert json.loads((target / "capabilities-graph-hub.json").read_text())["entries"] == ["v2"]
    # hub local untouched
    assert (tmp_path / "hubtarget" / "local" / "notes.json").read_text() == '{"local":1}\n'


def test_corrupt_master_is_refused_not_distributed(tmp_path):
    # a master whose file no longer matches its own MANIFEST must NOT be applied
    master = _make_master(tmp_path / "master", {"tools/a.py": "v2\n"})
    (master / "tools/a.py").write_text("DRIFTED after manifest cut\n")   # master now corrupt
    target = tmp_path / "target" / "managed"
    _write(target / "tools/a.py", "v1\n")
    before = (target / "tools/a.py").read_text()

    rep = hu.upgrade(master, target, dry_run=False)
    assert rep["ok"] is False
    assert "aborted" in rep
    assert rep["applied"] == 0
    assert (target / "tools/a.py").read_text() == before   # target untouched by a refused upgrade


def _make_master_tree(root, spoke_files, hub_files=None):
    """A full master with spoke/ (managed+local skeleton) and optional hub/."""
    spoke_managed = _make_master(root / "spoke", spoke_files)
    _write(root / "spoke" / "local" / "sessions" / ".gitkeep", "")
    if hub_files is not None:
        hm = Path(root) / "hub" / "managed"
        for rel, txt in hub_files.items():
            _write(hm / rel, txt)
        m = hu.build_manifest(hm, generated_at="2026-01-01T00:00:00Z")
        (hm / hu.MANIFEST_NAME).write_text(json.dumps(m, indent=2) + "\n")
        _write(Path(root) / "hub" / "local" / ".gitkeep", "")
    return root


def test_install_fresh_new_spoke(tmp_path):
    master = _make_master_tree(tmp_path / "master", {"tools/a.py": "v2\n", "skills/x.md": "s\n"})
    # the master is itself a live spoke: its local/ holds the master's OWN work-state.
    _write(master / "spoke" / "local" / "lugs" / "bytype" / "task" / "open" / "masters-lug.json", '{"id":"masters"}\n')
    _write(master / "spoke" / "local" / "WAI-State.json", '{"owner":"master"}\n')
    _write(master / "spoke" / "local" / "sessions" / "s-master" / "track.jsonl", '{"turn":1}\n')
    new_spoke = tmp_path / "new-spoke"
    new_spoke.mkdir()
    rep = hu.install(master, new_spoke, include_hub=False)
    assert rep["ok"] is True
    assert rep["fresh"] is True
    assert rep["verify"]["ok"] is True
    assert (new_spoke / "WAI-Harness" / "spoke" / "managed" / "tools" / "a.py").read_text() == "v2\n"
    # an EMPTY local skeleton is scaffolded (dirs + .gitkeep)
    local = new_spoke / "WAI-Harness" / "spoke" / "local"
    assert (local / "sessions").is_dir()
    assert (local / "lugs" / "bytype" / "task" / "open").is_dir()
    # CRITICAL: NONE of the master's local work-state may leak into the new spoke
    assert not (local / "lugs" / "bytype" / "task" / "open" / "masters-lug.json").exists()
    assert not (local / "WAI-State.json").exists()
    assert not (local / "sessions" / "s-master").exists()


def test_install_existing_spoke_is_non_destructive(tmp_path):
    master = _make_master_tree(tmp_path / "master", {"tools/a.py": "v2\n"})
    spoke = tmp_path / "existing"
    # a pre-existing v3 tree that must survive verbatim
    _write(spoke / "WAI-Spoke" / "WAI-State.json", '{"v3":true}\n')
    _write(spoke / "WAI-Spoke" / "sessions" / "s" / "track.jsonl", '{"turn":1}\n')
    _write(spoke / "CLAUDE.md", "v3 readme\n")

    rep = hu.install(master, spoke)
    assert rep["ok"] is True
    assert rep["non_destructive"] is True
    # v3 tree byte-for-byte intact; v4 folder added beside it
    assert (spoke / "WAI-Spoke" / "WAI-State.json").read_text() == '{"v3":true}\n'
    assert (spoke / "WAI-Spoke" / "sessions" / "s" / "track.jsonl").read_text() == '{"turn":1}\n'
    assert (spoke / "CLAUDE.md").read_text() == "v3 readme\n"
    assert (spoke / "WAI-Harness").is_dir()
    assert {"WAI-Spoke", "WAI-Harness", "CLAUDE.md"} <= set(p.name for p in spoke.iterdir())


def test_install_ships_always_clean_gitignore(tmp_path):
    # the master's .gitignore must travel with a fresh install so local/ churn
    # cannot dirty the tracked tree (the always-clean invariant)
    master = _make_master_tree(tmp_path / "master", {"tools/a.py": "v2\n"})
    (master / ".gitignore").write_text("spoke/local/**\n!spoke/local/**/\n!**/.gitkeep\n")
    spoke = tmp_path / "spoke"
    spoke.mkdir()
    rep = hu.install(master, spoke)
    assert rep["ok"] is True
    assert rep.get("gitignore_shipped") is True
    gi = (spoke / "WAI-Harness" / ".gitignore").read_text()
    assert "spoke/local/**" in gi          # runtime state ignored
    assert "!**/.gitkeep" in gi            # skeleton kept


def test_install_hub_proves_hub_payload(tmp_path):
    master = _make_master_tree(tmp_path / "master", {"tools/a.py": "v2\n"},
                               hub_files={"capabilities-graph-hub.json": '{"entries":[1,2,3]}\n'})
    hub_spoke = tmp_path / "hub"
    _write(hub_spoke / "WAI-Spoke" / "WAI-State.json", '{"role":"hub"}\n')
    rep = hu.install(master, hub_spoke, include_hub=True)
    assert rep["ok"] is True
    assert rep["verify"]["ok"] is True and rep["verify_hub"]["ok"] is True
    # hub functionality payload is intact + loadable from the v4 folder
    cg = json.loads((hub_spoke / "WAI-Harness" / "hub" / "managed" / "capabilities-graph-hub.json").read_text())
    assert cg["entries"] == [1, 2, 3]


def test_manifest_excludes_build_artifacts(tmp_path):
    managed = tmp_path / "managed"
    _write(managed / "tools" / "a.py", "code\n")
    _write(managed / "tools" / "__pycache__" / "a.cpython-312.pyc", "BYTECODE")
    _write(managed / ".pytest_cache" / "v" / "x", "cache")
    m = hu.build_manifest(managed, generated_at="2026-01-01T00:00:00Z")
    assert "tools/a.py" in m["files"]
    assert not any("pycache" in f or "pytest_cache" in f or f.endswith(".pyc") for f in m["files"])


def test_idempotent_second_upgrade_is_all_unchanged(tmp_path):
    master = _make_master(tmp_path / "master", {"tools/a.py": "v2\n"})
    target = tmp_path / "target" / "managed"
    hu.upgrade(master, target, dry_run=False)
    hm = hu.compute_home_map(master, target)
    assert hm["add"] == [] and hm["change"] == []
    assert "tools/a.py" in hm["unchanged"]
