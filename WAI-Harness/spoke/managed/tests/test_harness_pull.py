"""Acceptance proof: harness_upgrade.pull() — the pull-on-spin-up self-update
(Phase 2.5, task-v4-keystone-rollout-wiring). Hermetic: synthetic master + spoke
on a tmp tree. Proves the cheap no-op-when-current path, the upgrade-when-behind
path, local/ is never touched, and presence-guards (no-harness / no-master).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import harness_upgrade as hu  # noqa: E402


def _write(p: Path, text: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _master(tmp_path, files):
    managed = tmp_path / "mywheel" / "WAI-Harness" / "spoke" / "managed"
    for rel, content in files.items():
        _write(managed / rel, content)
    m = hu.build_manifest(str(managed), generated_at="2026-01-01T00:00:00Z")
    (managed / hu.MANIFEST_NAME).write_text(json.dumps(m, indent=2) + "\n")
    return tmp_path / "mywheel" / "WAI-Harness"


def _spoke(tmp_path, files, *, with_local=True):
    root = tmp_path / "spokeA"
    managed = root / "WAI-Harness" / "spoke" / "managed"
    for rel, content in files.items():
        _write(managed / rel, content)
    m = hu.build_manifest(str(managed), generated_at="2026-01-01T00:00:00Z")
    (managed / hu.MANIFEST_NAME).write_text(json.dumps(m, indent=2) + "\n")
    if with_local:
        _write(root / "WAI-Harness" / "spoke" / "local" / "WAI-State.json", '{"v":4,"local":true}')
    return root


def test_current_spoke_is_cheap_noop(tmp_path):
    files = {"a.py": "x\n", "skills/b.md": "# b\n"}
    master = _master(tmp_path, files)
    spoke = _spoke(tmp_path, files)
    res = hu.pull(str(spoke), str(master))
    assert res["status"] == "current" and res["current"] is True and res["pulled"] == 0


def test_behind_spoke_upgrades(tmp_path):
    master = _master(tmp_path, {"a.py": "NEW\n", "b.py": "added\n"})
    spoke = _spoke(tmp_path, {"a.py": "OLD\n"})  # a.py changed + b.py missing
    res = hu.pull(str(spoke), str(master))
    assert res["status"] == "upgraded" and res["current"] is True and res["ok"] is True
    assert res["pulled"] >= 2
    # now current
    assert hu.pull(str(spoke), str(master))["status"] == "current"


def test_dry_run_reports_behind_without_writing(tmp_path):
    master = _master(tmp_path, {"a.py": "NEW\n"})
    spoke = _spoke(tmp_path, {"a.py": "OLD\n"})
    res = hu.pull(str(spoke), str(master), dry_run=True)
    assert res["status"] == "behind" and res["pending"] >= 1 and res["current"] is False
    # nothing written: still behind on a real (non-dry) re-check would upgrade
    assert (spoke / "WAI-Harness" / "spoke" / "managed" / "a.py").read_text() == "OLD\n"


def test_local_tree_never_touched(tmp_path):
    master = _master(tmp_path, {"a.py": "NEW\n"})
    spoke = _spoke(tmp_path, {"a.py": "OLD\n"})
    local = spoke / "WAI-Harness" / "spoke" / "local" / "WAI-State.json"
    before = local.read_text()
    hu.pull(str(spoke), str(master))
    assert local.read_text() == before  # managed upgrade left local/ identical


def test_no_harness_is_noop_not_error(tmp_path):
    master = _master(tmp_path, {"a.py": "x\n"})
    bare = tmp_path / "bare"
    (bare / "WAI-Spoke").mkdir(parents=True)  # v3-only, no WAI-Harness
    res = hu.pull(str(bare), str(master))
    assert res["status"] == "no-harness" and res["pulled"] == 0


def test_no_master_is_noop_not_error(tmp_path):
    spoke = _spoke(tmp_path, {"a.py": "x\n"})
    res = hu.pull(str(spoke), str(tmp_path / "does-not-exist" / "WAI-Harness"))
    assert res["status"] == "no-master" and res["pulled"] == 0
