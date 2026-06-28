"""test_validate_canonical_v4_paths.py

AP test: validate_canonical resolves its lug roots through wai_paths instead of
hardcoding WAI-Spoke, so it actually reads the v4 store on a v4-only spoke.

Invariant verified:
  WAI_HARNESS_MODE=v4-only -> lug discovery (_all_lug_ids and run's lugs_root
  scan) reads from WAI-Harness/spoke/local/lugs. A lug placed ONLY in the v4
  tree is FOUND (non-empty) — proving it is not looking at a phantom WAI-Spoke.
"""
import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import validate_canonical  # noqa: E402 — must come after sys.path insert


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _v4_lugs_base(spoke_root):
    return os.path.join(spoke_root, "WAI-Harness", "spoke", "local", "lugs")


def _make_v4_lug(spoke_root):
    """Write a minimal open implementation lug into the v4 lugs tree."""
    lug_dir = os.path.join(
        _v4_lugs_base(spoke_root), "bytype", "implementation", "open")
    os.makedirs(lug_dir, exist_ok=True)
    lug = {
        "id": "impl-v4-canonical-001",
        "type": "implementation",
        "status": "open",
        "title": "V4 path-resolution probe lug",
    }
    path = os.path.join(lug_dir, "impl-v4-canonical-001.json")
    with open(path, "w") as fh:
        json.dump(lug, fh)
    return lug


def _make_contract(spoke_root):
    """Place the canonical contract spec in the v4 lugs spec/active tree."""
    spec_dir = os.path.join(
        _v4_lugs_base(spoke_root), "bytype", "spec", "active")
    os.makedirs(spec_dir, exist_ok=True)
    contract = {
        "id": "spec-canonical-object-contract-v1",
        "type": "spec",
        "status": "active",
        "subject_id": "canonical-object",
        "title": "Canonical Object Contract v1",
        "contract": {"lug": {"applies_to_types": ["implementation"]}},
    }
    path = os.path.join(spec_dir, "spec-canonical-object-contract-v1.json")
    with open(path, "w") as fh:
        json.dump(contract, fh)
    return contract


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class TestV4OnlyMode:
    """WAI_HARNESS_MODE=v4-only: discovery reads from WAI-Harness/spoke/local/lugs."""

    def test_all_lug_ids_finds_v4_lug(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        _make_v4_lug(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        ids = validate_canonical._all_lug_ids(tmp)
        assert "impl-v4-canonical-001" in ids, (
            f"v4 lug not discovered — got {ids}; "
            "validator is reading a phantom WAI-Spoke instead of the v4 store")

    def test_run_scans_v4_lug(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        _make_contract(tmp)
        _make_v4_lug(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        violations, checked = validate_canonical.run(tmp)
        # contract loaded from v4 tree -> not the contract_not_found sentinel
        assert not any(
            v.get("rule") == "contract_present" for v in violations), (
            f"contract not found in v4 lugs tree: {violations}")
        # the v4 lug + the contract spec were both scanned
        assert checked >= 1, "run() scanned nothing in the v4 lugs tree"

    def test_no_phantom_wai_spoke(self, monkeypatch, tmp_path):
        """Even when an empty WAI-Spoke coexists, v4-only finds the v4 lug."""
        tmp = str(tmp_path)
        os.makedirs(os.path.join(tmp, "WAI-Spoke"), exist_ok=True)  # empty v3 dir
        _make_v4_lug(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        ids = validate_canonical._all_lug_ids(tmp)
        assert "impl-v4-canonical-001" in ids
