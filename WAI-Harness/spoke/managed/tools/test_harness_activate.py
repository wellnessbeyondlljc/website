"""Tracked test-at-birth for tools/harness_activate.py — the dormant on-load
activation trigger AND its master-parity gate.

Source-of-truth note: harness_activate.py is framework-owned (tools/), but its
only prior test lived in the gitignored managed/ tree, so the parity gate had no
tracked coverage (cutover-blocker C-1). This file is the tracked source test.

Proves the safety design:
  - DORMANT: an upgraded spoke with no ACTIVATE marker migrates NOTHING on load
  - NOTICE: check_on_load reports "v4 available (dormant)" — the agent notices
  - OPT-IN: only an explicit WAI-Harness/ACTIVATE marker triggers migration
  - DRY-RUN first: migrate() previews without writing
  - NON-DESTRUCTIVE: v3 state is copied into v4 local/, v3 left intact
  - IDEMPOTENT: a second load after activation is a no-op
  - NO-ORPHAN visibility: unmapped v3 categories are reported, not dropped
  - PARITY GATE: stale/absent master refuses activation; current master allows it;
    --force overrides and records it
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness_activate as ha  # noqa: E402


def _spoke(tmp, upgraded=True, v3_state=True):
    root = tmp / "spoke"
    (root / "WAI-Spoke").mkdir(parents=True)
    if v3_state:
        (root / "WAI-Spoke" / "WAI-State.json").write_text('{"v3":true}\n')
        (root / "WAI-Spoke" / "sessions" / "s1").mkdir(parents=True)
        (root / "WAI-Spoke" / "sessions" / "s1" / "track.jsonl").write_text('{"turn":1}\n')
        (root / "WAI-Spoke" / "lugs").mkdir()
        (root / "WAI-Spoke" / "lugs" / "l.json").write_text('{"id":"l"}\n')
        (root / "WAI-Spoke" / "scratchpad.txt").write_text("unmapped\n")   # orphan (not in home-map)
    if upgraded:
        (root / "WAI-Harness" / "spoke" / "local").mkdir(parents=True)
    return root


def _master(tmp, files=None):
    """A tmp master WAI-Harness dir with spoke/managed/MANIFEST.json.

    files: {rel: {"md5": ...}} recorded in the master manifest. None/{} = an empty
    manifest, which compare_to_master treats as trivially CURRENT (no missing/stale)."""
    m = tmp / "master" / "WAI-Harness"
    (m / "spoke" / "managed").mkdir(parents=True)
    (m / "spoke" / "managed" / "MANIFEST.json").write_text(json.dumps({"files": files or {}}))
    return m


# ---- dormant / opt-in / migration behavior ---------------------------------

def test_dormant_by_default_no_migration(tmp_path):
    spoke = _spoke(tmp_path)
    assert ha.status(spoke) == "upgraded_dormant"
    out = ha.check_on_load(spoke)
    assert out["status"] == "upgraded_dormant"
    assert "dormant" in out["message"].lower()
    assert "result" not in out                                   # nothing ran
    assert not (spoke / "WAI-Harness" / "spoke" / "local" / "WAI-State.json").exists()


def test_not_upgraded_is_noop(tmp_path):
    spoke = _spoke(tmp_path, upgraded=False)
    assert ha.status(spoke) == "not_upgraded"
    assert ha.activate(spoke, dry_run=False)["action"] == "none"


def test_migrate_dry_run_writes_nothing(tmp_path):
    spoke = _spoke(tmp_path)
    rep = ha.migrate(spoke, dry_run=True)
    assert rep["dry_run"] is True
    assert any(m["src"] == "WAI-Spoke/WAI-State.json" for m in rep["migrated"])
    assert any(m["src"] == "WAI-Spoke/sessions" for m in rep["migrated"])
    assert not (spoke / "WAI-Harness" / "spoke" / "local" / "WAI-State.json").exists()
    assert "scratchpad.txt" in rep["orphans_left_in_v3"]


def test_opt_in_activation_migrates_non_destructively(tmp_path):
    spoke = _spoke(tmp_path)
    (spoke / "WAI-Harness" / ha.ACTIVATE_MARKER).write_text("")     # explicit opt-in
    assert ha.status(spoke) == "activation_requested"

    out = ha.check_on_load(spoke)                                  # the real on-load run
    assert out["status"] == "activation_requested"
    assert out["result"]["action"].startswith("migrate")

    # v3 state COPIED into v4 local/
    assert (spoke / "WAI-Harness" / "spoke" / "local" / "WAI-State.json").read_text() == '{"v3":true}\n'
    assert (spoke / "WAI-Harness" / "spoke" / "local" / "sessions" / "s1" / "track.jsonl").exists()
    assert (spoke / "WAI-Harness" / "spoke" / "local" / "lugs" / "l.json").exists()
    # v3 left intact (non-destructive — instant fallback)
    assert (spoke / "WAI-Spoke" / "WAI-State.json").read_text() == '{"v3":true}\n'
    assert (spoke / "WAI-Spoke" / "sessions" / "s1" / "track.jsonl").exists()
    # now activated
    assert ha.status(spoke) == "activated"


def test_idempotent_second_load_is_noop(tmp_path):
    spoke = _spoke(tmp_path)
    (spoke / "WAI-Harness" / ha.ACTIVATE_MARKER).write_text("")
    ha.check_on_load(spoke)                       # first load migrates
    assert ha.status(spoke) == "activated"
    # tamper v4 local to detect a re-copy, then load again
    (spoke / "WAI-Harness" / "spoke" / "local" / "WAI-State.json").write_text('{"edited":true}\n')
    out = ha.check_on_load(spoke)                 # second load
    assert out["status"] == "activated"
    assert "result" not in out                    # no re-migration
    assert (spoke / "WAI-Harness" / "spoke" / "local" / "WAI-State.json").read_text() == '{"edited":true}\n'


# ---- parity gate (cutover-blocker C-1: was untested) ------------------------

def test_parity_gate_current_master_activates(tmp_path):
    """A master at parity (empty manifest -> trivially current) allows activation."""
    spoke = _spoke(tmp_path)
    (spoke / "WAI-Harness" / ha.ACTIVATE_MARKER).write_text("")
    master = _master(tmp_path)
    rep = ha.activate(spoke, dry_run=False, master_dir=str(master))
    assert rep["action"].startswith("migrate")
    assert rep.get("blocked") is not True
    assert ha.status(spoke) == "activated"


def test_parity_gate_stale_master_refused(tmp_path):
    """A master recording a file the install lacks -> STALE -> activation refused."""
    spoke = _spoke(tmp_path)
    (spoke / "WAI-Harness" / ha.ACTIVATE_MARKER).write_text("")
    master = _master(tmp_path, files={"tools/x.py": {"md5": "deadbeef"}})
    rep = ha.activate(spoke, dry_run=False, master_dir=str(master))
    assert rep.get("blocked") is True
    assert rep["blockers"]
    assert ha.status(spoke) == "activation_requested"     # NOT activated


def test_parity_gate_missing_master_manifest_refused(tmp_path):
    """No master MANIFEST -> cannot prove currency -> refused."""
    spoke = _spoke(tmp_path)
    (spoke / "WAI-Harness" / ha.ACTIVATE_MARKER).write_text("")
    bare = tmp_path / "bare_master" / "WAI-Harness"
    bare.mkdir(parents=True)                                # no MANIFEST.json
    rep = ha.activate(spoke, dry_run=False, master_dir=str(bare))
    assert rep.get("blocked") is True
    assert any("MANIFEST not found" in b for b in rep["blockers"])
    assert ha.status(spoke) == "activation_requested"


def test_parity_gate_force_overrides_stale(tmp_path):
    """--force activates against a stale master and records forced=True."""
    spoke = _spoke(tmp_path)
    (spoke / "WAI-Harness" / ha.ACTIVATE_MARKER).write_text("")
    master = _master(tmp_path, files={"tools/x.py": {"md5": "deadbeef"}})
    rep = ha.activate(spoke, dry_run=False, master_dir=str(master), force=True)
    assert rep["action"].startswith("migrate")
    assert rep["forced"] is True
    assert ha.status(spoke) == "activated"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
