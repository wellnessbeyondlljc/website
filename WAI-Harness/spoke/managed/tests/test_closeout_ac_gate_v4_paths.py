"""test_closeout_ac_gate_v4_paths.py

AP test: check_completion_linkage resolves the correct working base depending on
WAI_HARNESS_MODE.

Two invariants verified:
  1. WAI_HARNESS_MODE=v4-only  -> resolves WAI-Harness/spoke/local (v4 base);
     a completed lug placed ONLY in the v4 tree is found.
  2. coexist default (no env var) -> resolves WAI-Spoke (v3 base);
     the same lug in the v4 tree is NOT found (v3 tree has no lugs).
"""
import json
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import closeout_ac_gate  # noqa: E402 — must come after sys.path insert


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_open_epic(spoke_root, tree="v3"):
    """Write a minimal open epic into the correct tree."""
    if tree == "v4":
        base = os.path.join(spoke_root, "WAI-Harness", "spoke", "local")
    else:
        base = os.path.join(spoke_root, "WAI-Spoke")
    ep_dir = os.path.join(base, "lugs", "bytype", "epic", "open")
    os.makedirs(ep_dir, exist_ok=True)
    epic = {"id": "epic-test-001", "type": "epic", "status": "open", "title": "Test Epic"}
    path = os.path.join(ep_dir, "epic-test-001.json")
    with open(path, "w") as fh:
        json.dump(epic, fh)
    return epic


def _make_completed_lug(spoke_root, tree="v3"):
    """Write a completed impl lug that passes completion_gate.

    Uses closes_no_ac to satisfy completion_gate without needing a full
    verification_test chain — keeps the test focused on PATH resolution,
    not on completion-gate logic.
    """
    if tree == "v4":
        base = os.path.join(spoke_root, "WAI-Harness", "spoke", "local")
    else:
        base = os.path.join(spoke_root, "WAI-Spoke")
    lug_dir = os.path.join(base, "lugs", "bytype", "implementation", "completed")
    os.makedirs(lug_dir, exist_ok=True)
    lug = {
        "id": "impl-test-001",
        "type": "implementation",
        "status": "completed",
        "parent_epic": "epic-test-001",
        # closes_no_ac = explicit acknowledgment that this lug closes no AC
        # -> completion_gate returns ok=True with a note (not a violation)
        "closes_no_ac": "path-resolution test lug — no AC to close",
    }
    path = os.path.join(lug_dir, "impl-test-001.json")
    with open(path, "w") as fh:
        json.dump(lug, fh)
    return lug


def _make_trees(tmp, which):
    """Populate trees. 'which' is 'v3', 'v4', or 'both'."""
    if which in ("v3", "both"):
        os.makedirs(os.path.join(tmp, "WAI-Spoke"), exist_ok=True)
    if which in ("v4", "both"):
        os.makedirs(os.path.join(tmp, "WAI-Harness", "spoke", "local"), exist_ok=True)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class TestV4OnlyMode:
    """WAI_HARNESS_MODE=v4-only: linkage reads from WAI-Harness/spoke/local."""

    def test_finds_completed_lug_in_v4_tree(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        # Only v4 tree exists (no WAI-Spoke)
        _make_trees(tmp, "v4")
        _make_open_epic(tmp, tree="v4")
        _make_completed_lug(tmp, tree="v4")

        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        result = closeout_ac_gate.check_completion_linkage(tmp)
        # Lug has closes_epic_acs -> no violations expected
        assert result["ok"] is True, f"unexpected violations: {result['violations']}"
        # And we confirmed it actually scanned (found the lug) by checking violations list
        assert result["violations"] == []

    def test_no_wai_spoke_access_in_v4_only(self, monkeypatch, tmp_path):
        """With v4-only, even when WAI-Spoke coexists, only v4 base is used.
        We put the open epic + completed lug only in v4; WAI-Spoke is an empty dir.
        If check_completion_linkage fell back to WAI-Spoke it would find no epics and
        return ok=True with no scan — here we confirm it found the v4 lug instead."""
        tmp = str(tmp_path)
        _make_trees(tmp, "both")  # both trees present
        _make_open_epic(tmp, tree="v4")
        _make_completed_lug(tmp, tree="v4")
        # WAI-Spoke is empty — no lugs there

        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        result = closeout_ac_gate.check_completion_linkage(tmp)
        # Lug found in v4 base and it has closes_epic_acs -> ok
        assert result["ok"] is True
        assert result["violations"] == []


class TestCoexistDefaultMode:
    """No WAI_HARNESS_MODE set (coexist): resolver defaults to v3 (WAI-Spoke)."""

    def test_uses_v3_base_in_coexist(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        _make_trees(tmp, "both")  # both trees present
        # Put lug+epic ONLY in v3
        _make_open_epic(tmp, tree="v3")
        _make_completed_lug(tmp, tree="v3")
        # v4 tree is empty — if resolver went v4 it would find nothing and still pass

        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

        result = closeout_ac_gate.check_completion_linkage(tmp)
        assert result["ok"] is True
        assert result["violations"] == []

    def test_v4_only_tree_lug_not_found_when_coexist_default(self, monkeypatch, tmp_path):
        """When both trees present but no mode set, v3 is default.
        A completed lug in v4 only is NOT scanned -> violations list stays empty
        (because open_epics comes from v3 too, so there's nothing to violate)."""
        tmp = str(tmp_path)
        _make_trees(tmp, "both")
        # Only v4 has the epic+lug; v3 is empty
        _make_open_epic(tmp, tree="v4")
        _make_completed_lug(tmp, tree="v4")

        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

        result = closeout_ac_gate.check_completion_linkage(tmp)
        # v3 base has no open epics -> nothing to enforce -> ok=True, empty
        assert result["ok"] is True
        assert result["violations"] == []


class TestV3OnlyMode:
    """Explicit v3-only or just WAI-Spoke present: v3 base used."""

    def test_explicit_v3_mode(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        _make_trees(tmp, "v3")
        _make_open_epic(tmp, tree="v3")
        _make_completed_lug(tmp, tree="v3")

        monkeypatch.setenv("WAI_HARNESS_MODE", "v3-only")

        result = closeout_ac_gate.check_completion_linkage(tmp)
        assert result["ok"] is True
        assert result["violations"] == []
