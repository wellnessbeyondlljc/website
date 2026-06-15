"""test_advisor_context_refresh_v4_paths.py

AP test: advisor_context_refresh resolves the correct working base depending on
WAI_HARNESS_MODE.

Two invariants verified:
  1. WAI_HARNESS_MODE=v4-only  -> resolves v4 advisors dir (WAI-Harness/spoke/advisors)
     and v4 working base (WAI-Harness/spoke/local); advisors + WAI-State only in v4
     tree are found; spoke-profile written into v4 base.
  2. coexist default (no env var) -> resolves v3 advisors dir (WAI-Spoke/advisors)
     and v3 working base (WAI-Spoke); v3 tree used exclusively.

Only the live reads/writes (advisors dir, WAI-State.json, spoke-profile.json) are
tested. Trash-mirror paths remain literal ("WAI-Spoke/advisors/...") per spec.
"""
import json
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import wai_paths  # noqa: E402

# Import the two public functions under test.
# promote_to_spoke_profile and the resolver logic inside refresh_advisor are
# tested indirectly through main() and the module-level helpers.
import advisor_context_refresh as acr  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_v3_tree(tmp):
    """Create a minimal v3 spoke tree (WAI-Spoke/ present)."""
    wai_spoke = os.path.join(tmp, "WAI-Spoke")
    os.makedirs(os.path.join(wai_spoke, "advisors"), exist_ok=True)
    return wai_spoke


def _make_v4_tree(tmp):
    """Create a minimal v4 spoke tree (WAI-Harness/spoke/local + sibling advisors)."""
    local = os.path.join(tmp, "WAI-Harness", "spoke", "local")
    advisors = os.path.join(tmp, "WAI-Harness", "spoke", "advisors")
    os.makedirs(local, exist_ok=True)
    os.makedirs(advisors, exist_ok=True)
    return local, advisors


def _write_state(base_dir, spoke_id="test-spoke", spoke_name="Test Spoke"):
    """Write a minimal WAI-State.json into base_dir."""
    state = {
        "wheel": {
            "spoke_id": spoke_id,
            "name": spoke_name,
            "hub_path": None,
        }
    }
    path = os.path.join(base_dir, "WAI-State.json")
    with open(path, "w") as fh:
        json.dump(state, fh)
    return path


def _make_advisor(advisors_root, name="test-advisor"):
    """Create a minimal advisor directory with a feeds.yaml."""
    advisor_dir = os.path.join(advisors_root, name)
    context_dir = os.path.join(advisor_dir, "context")
    os.makedirs(context_dir, exist_ok=True)
    # Minimal feeds.yaml — no real feeds so refresh_advisor completes quickly.
    feeds_yaml = "feeds: []\nrefresh_interval_days: 7\nkeep_snapshots: 5\n"
    with open(os.path.join(advisor_dir, "feeds.yaml"), "w") as fh:
        fh.write(feeds_yaml)
    return advisor_dir


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class TestV4OnlyMode:
    """WAI_HARNESS_MODE=v4-only: all paths resolve to WAI-Harness/spoke/..."""

    def test_advisors_dir_resolves_v4(self, tmp_path, monkeypatch):
        """wai_paths.advisors_dir() returns WAI-Harness/spoke/advisors in v4-only."""
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
        _make_v4_tree(str(tmp_path))

        result = wai_paths.advisors_dir(str(tmp_path))
        expected = str(tmp_path / "WAI-Harness" / "spoke" / "advisors")
        assert result == expected

    def test_resolve_wai_root_returns_v4_base(self, tmp_path, monkeypatch):
        """resolve_wai_root() returns WAI-Harness/spoke/local in v4-only."""
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
        _make_v4_tree(str(tmp_path))

        base, mode = wai_paths.resolve_wai_root(str(tmp_path))
        assert mode == "v4"
        assert base == str(tmp_path / "WAI-Harness" / "spoke" / "local")

    def test_wai_state_read_from_v4_base(self, tmp_path, monkeypatch):
        """WAI-State.json is read from WAI-Harness/spoke/local, NOT WAI-Spoke."""
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
        local, advisors = _make_v4_tree(str(tmp_path))
        # Write state ONLY in v4 base; v3 tree intentionally absent.
        _write_state(local, spoke_id="v4-spoke", spoke_name="V4 Spoke")

        base, mode = wai_paths.resolve_wai_root(str(tmp_path))
        state_path = os.path.join(base, "WAI-State.json")
        assert os.path.exists(state_path), "WAI-State.json must exist in v4 base"
        state = json.loads(open(state_path).read())
        assert state["wheel"]["spoke_id"] == "v4-spoke"

    def test_spoke_profile_written_to_v4_base(self, tmp_path, monkeypatch):
        """promote_to_spoke_profile writes spoke-profile.json into WAI-Harness/spoke/local."""
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
        local, _ = _make_v4_tree(str(tmp_path))
        _write_state(local)

        base_path = tmp_path / "WAI-Harness" / "spoke" / "local"
        acr.promote_to_spoke_profile(
            base_path,
            advisor_name="test-advisor",
            snapshot_file="snapshot-2099-01-01.md",
            synthesis="New major release announced. Breaking changes introduced. Migration required.",
            impact=8,
        )

        profile_path = base_path / "spoke-profile.json"
        assert profile_path.exists(), "spoke-profile.json must be written to v4 base"

        # Confirm NOT written to WAI-Spoke (absent + should not be created).
        v3_profile = tmp_path / "WAI-Spoke" / "spoke-profile.json"
        assert not v3_profile.exists(), "spoke-profile.json must NOT appear in WAI-Spoke in v4-only"

    def test_no_wai_spoke_access_in_v4_only(self, tmp_path, monkeypatch):
        """In v4-only, main() resolves advisors from v4 tree; WAI-Spoke must not be needed."""
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
        local, advisors = _make_v4_tree(str(tmp_path))
        _write_state(local)
        _make_advisor(advisors, name="ozi")

        # Resolve via the module functions the same way main() would.
        advisors_resolved = wai_paths.advisors_dir(str(tmp_path))
        base, mode = wai_paths.resolve_wai_root(str(tmp_path))

        assert advisors_resolved == str(tmp_path / "WAI-Harness" / "spoke" / "advisors")
        assert mode == "v4"
        assert base == str(tmp_path / "WAI-Harness" / "spoke" / "local")

        # The v3 WAI-Spoke directory must not need to exist.
        v3_spoke = tmp_path / "WAI-Spoke"
        assert not v3_spoke.exists(), "WAI-Spoke must not be created by v4-only resolution"

    def test_refresh_advisor_resolves_v4_base_via_spoke_root(self, tmp_path, monkeypatch):
        """refresh_advisor() uses the resolver when spoke_root is provided."""
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
        local, advisors = _make_v4_tree(str(tmp_path))
        _write_state(local)
        advisor_dir = _make_advisor(advisors, name="marge")

        result = acr.refresh_advisor(
            acr.Path(advisor_dir),
            hub_path=None,
            shared_context={},
            force=True,
            dry_run=False,
            quiet=True,
            spoke_root=str(tmp_path),
        )
        # Should refresh (no feeds = quick snapshot with header only)
        assert result["status"] == "refreshed"
        # Snapshot written inside the v4 advisors tree, not WAI-Spoke.
        snap = result["snapshot"]
        assert snap is not None
        assert "WAI-Harness" in snap
        assert "WAI-Spoke" not in snap


class TestCoexistDefaultMode:
    """coexist default (no env var, both trees present): v3 is used."""

    def test_advisors_dir_resolves_v3_in_coexist(self, tmp_path, monkeypatch):
        """With both trees present and no WAI_HARNESS_MODE, advisors_dir returns v3 path."""
        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
        _make_v3_tree(str(tmp_path))
        _make_v4_tree(str(tmp_path))

        result = wai_paths.advisors_dir(str(tmp_path))
        expected = str(tmp_path / "WAI-Spoke" / "advisors")
        assert result == expected

    def test_resolve_wai_root_returns_v3_base_in_coexist(self, tmp_path, monkeypatch):
        """With both trees present and no WAI_HARNESS_MODE, base is WAI-Spoke."""
        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
        _make_v3_tree(str(tmp_path))
        _make_v4_tree(str(tmp_path))

        base, mode = wai_paths.resolve_wai_root(str(tmp_path))
        assert mode == "v3"
        assert base == str(tmp_path / "WAI-Spoke")

    def test_wai_state_read_from_v3_base_in_coexist(self, tmp_path, monkeypatch):
        """WAI-State.json read from WAI-Spoke in coexist mode."""
        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
        v3 = _make_v3_tree(str(tmp_path))
        _make_v4_tree(str(tmp_path))
        _write_state(v3, spoke_id="v3-spoke", spoke_name="V3 Spoke")

        base, mode = wai_paths.resolve_wai_root(str(tmp_path))
        assert mode == "v3"
        state_path = os.path.join(base, "WAI-State.json")
        state = json.loads(open(state_path).read())
        assert state["wheel"]["spoke_id"] == "v3-spoke"

    def test_spoke_profile_written_to_v3_base_in_coexist(self, tmp_path, monkeypatch):
        """promote_to_spoke_profile writes spoke-profile.json into WAI-Spoke in coexist."""
        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
        v3 = _make_v3_tree(str(tmp_path))
        _make_v4_tree(str(tmp_path))
        _write_state(v3)

        v3_path = tmp_path / "WAI-Spoke"
        acr.promote_to_spoke_profile(
            v3_path,
            advisor_name="marge",
            snapshot_file="snapshot-2099-01-01.md",
            synthesis="Breaking change released. New API introduced. Deprecated endpoint removed.",
            impact=9,
        )

        profile_path = v3_path / "spoke-profile.json"
        assert profile_path.exists(), "spoke-profile.json must be written to WAI-Spoke in coexist"

    def test_refresh_advisor_resolves_v3_base_in_coexist(self, tmp_path, monkeypatch):
        """refresh_advisor() resolves v3 tree in coexist mode."""
        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
        v3 = _make_v3_tree(str(tmp_path))
        _make_v4_tree(str(tmp_path))
        _make_advisor(os.path.join(v3, "advisors"), name="archie")

        result = acr.refresh_advisor(
            acr.Path(os.path.join(v3, "advisors", "archie")),
            hub_path=None,
            shared_context={},
            force=True,
            dry_run=False,
            quiet=True,
            spoke_root=str(tmp_path),
        )
        assert result["status"] == "refreshed"
        snap = result["snapshot"]
        assert snap is not None
        # Snapshot is inside WAI-Spoke advisors (v3), not WAI-Harness.
        assert "WAI-Spoke" in snap
        assert "WAI-Harness" not in snap
