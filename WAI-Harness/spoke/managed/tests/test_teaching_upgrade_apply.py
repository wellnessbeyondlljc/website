"""Tests for tools/teaching_upgrade_apply.py"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from teaching_upgrade_apply import apply_upgrade, UPGRADE_FAILURES_FILE, BASE_VERSION_FILE


def _make_spoke(tmp: Path) -> Path:
    spoke = tmp / "spoke"
    (spoke / "WAI-Spoke" / "lugs" / "incoming").mkdir(parents=True, exist_ok=True)
    return spoke


def _make_consolidated(tmp: Path, teachings: list[dict]) -> Path:
    consolidated = {
        "id": "teaching-upgrade-base-v1-1-0",
        "type": "consolidated",
        "base_version": "1.1.0",
        "priority": "P2",
        "adopt_asap": False,
        "consolidates": [t["id"] for t in teachings],
        "teachings": teachings,
    }
    p = tmp / "upgrade.json"
    p.write_text(json.dumps(consolidated))
    return p


def _teaching_entry(tid: str, check_cmd: str, apply_cmd: str) -> dict:
    return {
        "id": tid,
        "title": f"Teaching {tid}",
        "verification_steps": [
            {"id": "v1", "description": "check", "check": check_cmd, "pass_criteria": "exit 0"}
        ],
        "apply_steps": [
            {"id": "a1", "description": "apply", "action": apply_cmd}
        ],
    }


# --- SKIP path: teaching already applied ---

def test_skip_when_verification_already_passes(tmp_path):
    spoke = _make_spoke(tmp_path)
    marker = spoke / "marker.txt"
    marker.write_text("done")

    teaching = _teaching_entry("t-skip", f"test -f {marker}", "echo noop")
    tf = _make_consolidated(tmp_path, [teaching])

    result = apply_upgrade(spoke, tf)
    assert result["ok"]
    assert result["outcomes"][0]["outcome"] == "SKIP"
    assert result["failure_count"] == 0
    assert result["version_written"] is True
    assert (spoke / BASE_VERSION_FILE).read_text().strip() == "1.1.0"


# --- ACCEPTED path: missing teaching applied and verified ---

def test_accepted_when_apply_fixes_verification(tmp_path):
    spoke = _make_spoke(tmp_path)
    marker = spoke / "WAI-Spoke" / "created-by-apply.txt"

    teaching = _teaching_entry(
        "t-accept",
        f"test -f {marker}",
        f"mkdir -p {marker.parent} && touch {marker}",
    )
    tf = _make_consolidated(tmp_path, [teaching])

    result = apply_upgrade(spoke, tf)
    assert result["ok"]
    assert result["outcomes"][0]["outcome"] == "ACCEPTED"
    assert result["failure_count"] == 0
    assert marker.exists()
    assert (spoke / BASE_VERSION_FILE).read_text().strip() == "1.1.0"


# --- FAILED path: apply cannot satisfy verification ---

def test_failed_when_apply_does_not_fix(tmp_path):
    spoke = _make_spoke(tmp_path)
    missing = spoke / "will-never-exist.txt"

    teaching = _teaching_entry(
        "t-fail",
        f"test -f {missing}",
        "echo intentionally-does-nothing",
    )
    tf = _make_consolidated(tmp_path, [teaching])

    result = apply_upgrade(spoke, tf)
    assert result["ok"]
    assert result["outcomes"][0]["outcome"] == "FAILED"
    assert result["failure_count"] == 1

    # Failure logged
    failures_path = spoke / UPGRADE_FAILURES_FILE
    assert failures_path.exists()
    lines = [json.loads(l) for l in failures_path.read_text().strip().splitlines()]
    assert any(l["id"] == "t-fail" for l in lines)

    # base_version NOT written when there are failures
    assert not (spoke / BASE_VERSION_FILE).exists()


# --- Failure continues to next teaching ---

def test_failure_does_not_stop_remaining_teachings(tmp_path):
    spoke = _make_spoke(tmp_path)
    good_marker = spoke / "good.txt"
    bad_marker = spoke / "bad-never.txt"

    teachings = [
        _teaching_entry("t-fail", f"test -f {bad_marker}", "echo noop"),
        _teaching_entry("t-ok", f"test -f {good_marker}", f"touch {good_marker}"),
    ]
    tf = _make_consolidated(tmp_path, teachings)

    result = apply_upgrade(spoke, tf)
    outcomes_by_id = {o["id"]: o["outcome"] for o in result["outcomes"]}
    assert outcomes_by_id["t-fail"] == "FAILED"
    assert outcomes_by_id["t-ok"] == "ACCEPTED"


# --- Basher-managed sentinel ---

def test_apply_step_skipped_for_basher_managed_dir(tmp_path):
    spoke = _make_spoke(tmp_path)
    basher_dir = spoke / "WAI-Spoke" / "basher-owned"
    basher_dir.mkdir(parents=True)
    (basher_dir / ".basher-managed").touch()

    protected = basher_dir / "config.json"
    teaching = _teaching_entry(
        "t-basher",
        f"test -f {protected}",
        f"echo protected > {protected}",
    )
    tf = _make_consolidated(tmp_path, [teaching])

    result = apply_upgrade(spoke, tf)
    # apply_step was skipped, so verification still fails -> FAILED
    assert result["outcomes"][0]["outcome"] == "FAILED"
    assert not protected.exists()
    # Confirm the skip is noted in apply_log
    apply_log = result["outcomes"][0].get("apply_log", [])
    assert any(s.get("skipped") and "basher" in s.get("reason", "") for s in apply_log)


# --- dry-run does not write files ---

def test_dry_run_does_not_write_anything(tmp_path):
    spoke = _make_spoke(tmp_path)
    marker = spoke / "dry-run-target.txt"

    teaching = _teaching_entry(
        "t-dry",
        f"test -f {marker}",
        f"touch {marker}",
    )
    tf = _make_consolidated(tmp_path, [teaching])

    result = apply_upgrade(spoke, tf, dry_run=True)
    assert result["dry_run"] is True
    assert not marker.exists()
    assert not (spoke / BASE_VERSION_FILE).exists()
    assert result["outcomes"][0]["outcome"] == "WOULD_APPLY"


# --- base_version file ---

def test_base_version_updated_on_full_success(tmp_path):
    spoke = _make_spoke(tmp_path)
    marker = spoke / "bv-marker.txt"
    marker.write_text("present")

    teaching = _teaching_entry("t-bv", f"test -f {marker}", "echo noop")
    tf = _make_consolidated(tmp_path, [teaching])

    apply_upgrade(spoke, tf)
    bv = (spoke / BASE_VERSION_FILE).read_text().strip()
    assert bv == "1.1.0"


# --- Error handling ---

def test_invalid_spoke_path(tmp_path):
    result = apply_upgrade(tmp_path / "nonexistent", tmp_path / "t.json")
    assert not result["ok"]
    assert "not found" in result["error"]


def test_non_consolidated_teaching_rejected(tmp_path):
    spoke = _make_spoke(tmp_path)
    tf = tmp_path / "bad.json"
    tf.write_text(json.dumps({"type": "individual", "id": "x"}))
    result = apply_upgrade(spoke, tf)
    assert not result["ok"]
    assert "consolidated" in result["error"]


def test_multiple_teachings_all_skip(tmp_path):
    spoke = _make_spoke(tmp_path)
    m1 = spoke / "m1.txt"
    m2 = spoke / "m2.txt"
    m1.write_text("x")
    m2.write_text("x")

    teachings = [
        _teaching_entry("t1", f"test -f {m1}", "echo noop"),
        _teaching_entry("t2", f"test -f {m2}", "echo noop"),
    ]
    tf = _make_consolidated(tmp_path, teachings)

    result = apply_upgrade(spoke, tf)
    assert all(o["outcome"] == "SKIP" for o in result["outcomes"])
    assert result["failure_count"] == 0
    assert result["version_written"] is True
