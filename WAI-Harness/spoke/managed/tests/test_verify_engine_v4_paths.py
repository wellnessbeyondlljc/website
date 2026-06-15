"""AP test: verify_engine._spoke_wai is harness-mode aware.

Invariants under test:
  1. WAI_HARNESS_MODE=v4-only -> _spoke_wai returns WAI-Harness/spoke/local.
  2. Default (coexist, no env) -> _spoke_wai returns WAI-Spoke (v3).
  3. v4-only with BOTH trees present -> still returns WAI-Harness/spoke/local.
  4. No trees present -> fallback to legacy WAI-Spoke (no crash).
"""
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import verify_engine  # noqa: E402


def _make_v3_tree(root: Path) -> Path:
    """Create a minimal WAI-Spoke tree under root; return root."""
    (root / "WAI-Spoke").mkdir(parents=True, exist_ok=True)
    return root


def _make_v4_tree(root: Path) -> Path:
    """Create a minimal WAI-Harness/spoke/local tree under root; return root."""
    (root / "WAI-Harness" / "spoke" / "local").mkdir(parents=True, exist_ok=True)
    return root


def _make_both_trees(root: Path) -> Path:
    """Create both v3 and v4 trees (coexist layout)."""
    _make_v3_tree(root)
    _make_v4_tree(root)
    return root


# ---------------------------------------------------------------------------
# Core harness-mode assertions
# ---------------------------------------------------------------------------

def test_v4_only_env_returns_v4_base(tmp_path, monkeypatch):
    """WAI_HARNESS_MODE=v4-only must return WAI-Harness/spoke/local."""
    _make_both_trees(tmp_path)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

    result = verify_engine._spoke_wai(tmp_path)

    assert result == tmp_path / "WAI-Harness" / "spoke" / "local"


def test_coexist_default_returns_v3_base(tmp_path, monkeypatch):
    """No explicit mode + both trees present -> coexist safe default -> WAI-Spoke."""
    _make_both_trees(tmp_path)
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

    result = verify_engine._spoke_wai(tmp_path)

    assert result == tmp_path / "WAI-Spoke"


def test_v4_only_with_both_trees_returns_v4(tmp_path, monkeypatch):
    """Even when both trees exist, v4-only forces the v4 base."""
    _make_both_trees(tmp_path)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

    result = verify_engine._spoke_wai(tmp_path)

    assert result == tmp_path / "WAI-Harness" / "spoke" / "local"
    # Confirm WAI-Spoke is NOT in the returned path.
    assert "WAI-Spoke" not in str(result)


def test_v3_only_tree_returns_v3_base(tmp_path, monkeypatch):
    """Only WAI-Spoke present (no WAI-Harness) -> v3 base."""
    _make_v3_tree(tmp_path)
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

    result = verify_engine._spoke_wai(tmp_path)

    assert result == tmp_path / "WAI-Spoke"


def test_v4_only_tree_returns_v4_base(tmp_path, monkeypatch):
    """Only WAI-Harness present (post-retirement) -> v4 base even without env."""
    _make_v4_tree(tmp_path)
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

    result = verify_engine._spoke_wai(tmp_path)

    assert result == tmp_path / "WAI-Harness" / "spoke" / "local"


def test_no_trees_fallback_no_crash(tmp_path, monkeypatch):
    """Neither tree exists -> resolver returns None -> legacy fallback WAI-Spoke path."""
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

    result = verify_engine._spoke_wai(tmp_path)

    # Must not raise; must return tmp_path / "WAI-Spoke" (legacy fallback).
    assert result == tmp_path / "WAI-Spoke"


# ---------------------------------------------------------------------------
# End-to-end: bolt written to v4 base in v4-only mode
# ---------------------------------------------------------------------------

def test_emit_ceremony_bolt_writes_to_v4_base(tmp_path, monkeypatch):
    """emit_ceremony_bolt in v4-only mode must write into WAI-Harness/spoke/local."""
    _make_both_trees(tmp_path)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

    import verify_engine as ve
    bolt = ve.emit_ceremony_bolt(
        "session-v4-test", "closeout", "standard",
        [{"step_id": "s1", "result": "pass"}],
        tmp_path, git_sha="aabbccdd",
    )

    bolt_path = Path(bolt["_bolt_path"])
    assert bolt_path.exists()
    # Must be under the v4 base, NOT under WAI-Spoke.
    v4_base = tmp_path / "WAI-Harness" / "spoke" / "local"
    assert str(bolt_path).startswith(str(v4_base)), (
        f"Expected bolt under {v4_base}, got {bolt_path}"
    )
    # Confirm nothing was written under WAI-Spoke.
    wai_spoke_bolts = tmp_path / "WAI-Spoke" / "bolts"
    assert not wai_spoke_bolts.exists(), "WAI-Spoke/bolts must NOT be created in v4-only mode"


def test_emit_ceremony_bolt_writes_to_v3_base_in_coexist(tmp_path, monkeypatch):
    """emit_ceremony_bolt in coexist (no env) mode must write into WAI-Spoke."""
    _make_both_trees(tmp_path)
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

    import verify_engine as ve
    bolt = ve.emit_ceremony_bolt(
        "session-v3-test", "closeout", "standard",
        [{"step_id": "s1", "result": "pass"}],
        tmp_path, git_sha="11223344",
    )

    bolt_path = Path(bolt["_bolt_path"])
    assert bolt_path.exists()
    v3_base = tmp_path / "WAI-Spoke"
    assert str(bolt_path).startswith(str(v3_base)), (
        f"Expected bolt under {v3_base}, got {bolt_path}"
    )
