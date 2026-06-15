"""Tests for tools/teaching_delivery_cut.py"""
import json
import sys
import shutil
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from teaching_delivery_cut import check, cut, auto, deliver_hot_patch, _teachings_root, HARD_CAP


def _make_hub(tmp: Path) -> Path:
    """Create a minimal hub structure in tmp."""
    root = tmp / "hub" / "WAI-Spoke" / "hub" / "teachings"
    for d in ["staging", "hot-patches", "consolidated", "archive"]:
        (root / d).mkdir(parents=True, exist_ok=True)
    manifest = {"current_version": "1.0.0", "cuts": []}
    (root / "base-version-manifest.json").write_text(json.dumps(manifest))
    return tmp / "hub"


def _make_teaching(staging: Path, name: str, priority: str = "P2") -> Path:
    adopt = priority in {"P0", "P1"}
    t = {
        "id": name,
        "title": f"Teaching {name}",
        "priority": priority,
        "adopt_asap": adopt,
        "verification_steps": [
            {"id": "v1", "description": "check", "check": "true", "pass_criteria": "exit 0"}
        ],
        "apply_steps": [
            {"id": "a1", "description": "apply", "action": "echo applied"}
        ],
    }
    p = staging / f"{name}.json"
    p.write_text(json.dumps(t))
    return p


def _make_spoke(tmp: Path, name: str) -> Path:
    spoke = tmp / name
    incoming = spoke / "WAI-Spoke" / "lugs" / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    return spoke


def _make_registry(tmp: Path, spokes: list[Path]) -> str:
    reg = {
        "wheels": [
            {"wheel_id": s.name, "path": str(s), "status": "active"}
            for s in spokes
        ]
    }
    reg_path = tmp / "hub-registry.json"
    reg_path.write_text(json.dumps(reg))
    return str(reg_path)


# Patch registry path for tests
import teaching_delivery_cut as _cut_mod


def test_check_empty_staging():
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        result = check(hub)
        assert result["staged_count"] == 0
        assert result["cut_needed"] is False
        assert result["hard_cap_exceeded"] is False


def test_check_with_staged():
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        staging = _teachings_root(hub) / "staging"
        _make_teaching(staging, "t-one")
        _make_teaching(staging, "t-two")
        result = check(hub)
        assert result["staged_count"] == 2
        assert result["cut_needed"] is True
        assert "t-one" in result["staged_ids"]


def test_cut_empty_staging_is_noop():
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        result = cut(hub)
        assert result["action"] == "noop"


def test_cut_produces_consolidated_teaching(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        staging = _teachings_root(hub) / "staging"
        _make_teaching(staging, "alpha")
        _make_teaching(staging, "beta")

        spoke = _make_spoke(Path(tmp), "spoke-a")
        reg = _make_registry(Path(tmp), [spoke])
        monkeypatch.setattr(_cut_mod, "HUB_REGISTRY_PATH", reg)

        result = cut(hub)
        assert result["action"] == "cut"
        assert result["teachings_consolidated"] == 2
        assert result["new_version"] == "1.1.0"

        # Consolidated file exists
        consolidated_dir = _teachings_root(hub) / "consolidated"
        files = list(consolidated_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["type"] == "consolidated"
        assert data["base_version"] == "1.1.0"
        assert set(data["consolidates"]) == {"alpha", "beta"}
        assert len(data["teachings"]) == 2


def test_cut_empties_staging(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        staging = _teachings_root(hub) / "staging"
        _make_teaching(staging, "gamma")

        monkeypatch.setattr(_cut_mod, "HUB_REGISTRY_PATH", _make_registry(Path(tmp), []))
        cut(hub)

        remaining = list(staging.glob("*.json"))
        assert remaining == []


def test_cut_archives_staged_files(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        staging = _teachings_root(hub) / "staging"
        _make_teaching(staging, "delta")

        monkeypatch.setattr(_cut_mod, "HUB_REGISTRY_PATH", _make_registry(Path(tmp), []))
        result = cut(hub)

        archive = _teachings_root(hub) / "archive" / "base-v1.1.0"
        assert (archive / "delta.json").exists()


def test_cut_updates_manifest(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        staging = _teachings_root(hub) / "staging"
        _make_teaching(staging, "epsilon")

        monkeypatch.setattr(_cut_mod, "HUB_REGISTRY_PATH", _make_registry(Path(tmp), []))
        cut(hub)

        manifest = json.loads((_teachings_root(hub) / "base-version-manifest.json").read_text())
        assert manifest["current_version"] == "1.1.0"
        assert len(manifest["cuts"]) == 1
        assert manifest["cuts"][0]["version"] == "1.1.0"


def test_cut_delivers_to_spoke(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        staging = _teachings_root(hub) / "staging"
        _make_teaching(staging, "zeta")

        spoke = _make_spoke(Path(tmp), "spoke-b")
        monkeypatch.setattr(_cut_mod, "HUB_REGISTRY_PATH", _make_registry(Path(tmp), [spoke]))

        result = cut(hub)
        assert "spoke-b" in result["delivered_to"]

        incoming = spoke / "WAI-Spoke" / "lugs" / "incoming"
        delivered = list(incoming.glob("teaching-upgrade-base-*.json"))
        assert len(delivered) == 1


def test_cut_skips_spoke_with_no_incoming(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        staging = _teachings_root(hub) / "staging"
        _make_teaching(staging, "eta")

        # Spoke without WAI-Spoke/lugs/incoming/
        spoke_path = Path(tmp) / "empty-spoke"
        spoke_path.mkdir()
        reg = {"wheels": [{"wheel_id": "empty-spoke", "path": str(spoke_path), "status": "active"}]}
        reg_path = Path(tmp) / "hub-registry.json"
        reg_path.write_text(json.dumps(reg))
        monkeypatch.setattr(_cut_mod, "HUB_REGISTRY_PATH", str(reg_path))

        result = cut(hub)
        assert "empty-spoke" in result["skipped_spokes"]


def test_auto_noop_when_empty():
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        result = auto(hub)
        assert result["action"] == "noop"


def test_auto_cuts_when_staged(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        hub = _make_hub(Path(tmp))
        staging = _teachings_root(hub) / "staging"
        _make_teaching(staging, "theta")

        monkeypatch.setattr(_cut_mod, "HUB_REGISTRY_PATH", _make_registry(Path(tmp), []))
        result = auto(hub)
        assert result["action"] == "cut"


def test_hot_patch_rejects_p2(tmp_path):
    t = {
        "id": "bad-hot-patch",
        "title": "Bad",
        "priority": "P2",
        "adopt_asap": False,
        "verification_steps": [
            {"id": "v1", "description": "d", "check": "true", "pass_criteria": "exit 0"}
        ],
        "apply_steps": [{"id": "a1", "description": "d", "action": "echo x"}],
    }
    f = tmp_path / "bad.json"
    f.write_text(json.dumps(t))

    hub = _make_hub(tmp_path)
    result = deliver_hot_patch(f, hub)
    assert not result["ok"]
    assert any("P0/P1" in e for e in result["errors"])


def test_hot_patch_delivers_p1(monkeypatch, tmp_path):
    t = {
        "id": "good-hot-patch",
        "title": "Good",
        "priority": "P1",
        "adopt_asap": True,
        "verification_steps": [
            {"id": "v1", "description": "d", "check": "true", "pass_criteria": "exit 0"}
        ],
        "apply_steps": [{"id": "a1", "description": "d", "action": "echo x"}],
    }
    f = tmp_path / "good.json"
    f.write_text(json.dumps(t))

    hub = _make_hub(tmp_path)
    spoke = _make_spoke(tmp_path, "spoke-hp")
    monkeypatch.setattr(_cut_mod, "HUB_REGISTRY_PATH", _make_registry(tmp_path, [spoke]))

    result = deliver_hot_patch(f, hub)
    assert result["ok"]
    assert "spoke-hp" in result["delivered_to"]
    assert (spoke / "WAI-Spoke" / "lugs" / "incoming" / "good.json").exists()
    assert (_teachings_root(hub) / "hot-patches" / "good.json").exists()
