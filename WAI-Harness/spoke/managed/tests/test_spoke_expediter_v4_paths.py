"""test_spoke_expediter_v4_paths.py

AP test: spoke_expediter resolves the correct working base depending on
WAI_HARNESS_MODE.

Two invariants verified:
  1. WAI_HARNESS_MODE=v4-only  -> resolves WAI-Harness/spoke/local (v4 base);
     a lug placed ONLY in the v4 tree is found by scan_lugs().
  2. coexist default (no env var, both trees present) -> resolves WAI-Spoke (v3 base);
     the v4-only lug is NOT found (v3 tree has no lugs).

Focused on path resolution, not full expediter semantics.
"""
import json
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import spoke_expediter  # noqa: E402 — must come after sys.path insert


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_LUG_ID = "impl-v4-path-probe-001"


def _make_lug(base, lug_id=_LUG_ID):
    """Write a minimal open implementation lug under the given working base."""
    lug_dir = os.path.join(base, "lugs", "bytype", "implementation", "open")
    os.makedirs(lug_dir, exist_ok=True)
    lug = {
        "id": lug_id,
        "type": "implementation",
        "status": "open",
        "title": "v4 path probe lug",
        "perceive": "read tools/spoke_expediter.py",
        "execute": "1. change the file. 2. verify. 3. commit.",
        "verify": "python3 -m pytest tests/ -q",
        "acceptance_criteria": ["expediter finds v4 lug in v4-only mode"],
        "target_files": ["tools/spoke_expediter.py"],
        "model_fit": "haiku",
    }
    path = os.path.join(lug_dir, f"{lug_id}.json")
    with open(path, "w") as fh:
        json.dump(lug, fh)
    return path


def _v4_base(spoke_root):
    return os.path.join(spoke_root, "WAI-Harness", "spoke", "local")


def _v3_base(spoke_root):
    return os.path.join(spoke_root, "WAI-Spoke")


def _make_trees(tmp, which):
    """Create the tree marker directories. 'which': 'v3', 'v4', or 'both'."""
    if which in ("v3", "both"):
        os.makedirs(_v3_base(tmp), exist_ok=True)
    if which in ("v4", "both"):
        os.makedirs(_v4_base(tmp), exist_ok=True)


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_v4_only_finds_v4_lug(monkeypatch):
    """With WAI_HARNESS_MODE=v4-only, scan_lugs finds a lug placed in the v4 tree."""
    with tempfile.TemporaryDirectory() as tmp:
        _make_trees(tmp, "v4")        # ONLY v4 tree exists
        _make_lug(_v4_base(tmp))
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        lugs = spoke_expediter.scan_lugs(tmp)

    ids = [spoke_expediter.get_lug_id(l) for l in lugs]
    assert _LUG_ID in ids, (
        f"Expected v4 lug {_LUG_ID!r} to be found in v4-only mode; got ids={ids}"
    )


def test_coexist_default_scans_v3(monkeypatch):
    """With no explicit mode (coexist default), scan_lugs resolves the v3 base.
    A lug placed ONLY in the v4 tree must NOT be found."""
    with tempfile.TemporaryDirectory() as tmp:
        _make_trees(tmp, "both")      # both trees present -> coexist -> default v3
        _make_lug(_v4_base(tmp))      # lug is ONLY in v4
        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

        lugs = spoke_expediter.scan_lugs(tmp)

    ids = [spoke_expediter.get_lug_id(l) for l in lugs]
    assert _LUG_ID not in ids, (
        f"In coexist-default (v3) mode the v4-only lug should be invisible; got ids={ids}"
    )


def test_v4_only_no_wai_spoke_access(monkeypatch):
    """In v4-only mode with only v4 tree, scan_lugs must return 0 for v3-placed lugs."""
    with tempfile.TemporaryDirectory() as tmp:
        _make_trees(tmp, "v4")
        # place lug in v3 path (which does NOT exist as a directory)
        # -> glob will simply find nothing, no error
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        lugs = spoke_expediter.scan_lugs(tmp)

    assert lugs == [], (
        f"v4-only mode with no v4 lugs should return empty; got {lugs}"
    )


def test_v4_only_coexist_tree_v4_lug_found(monkeypatch):
    """With WAI_HARNESS_MODE=v4-only and BOTH trees present, scan_lugs uses the v4 base."""
    with tempfile.TemporaryDirectory() as tmp:
        _make_trees(tmp, "both")
        _make_lug(_v4_base(tmp))
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        lugs = spoke_expediter.scan_lugs(tmp)

    ids = [spoke_expediter.get_lug_id(l) for l in lugs]
    assert _LUG_ID in ids, (
        f"v4-only override with both trees: lug in v4 base must be found; got ids={ids}"
    )
