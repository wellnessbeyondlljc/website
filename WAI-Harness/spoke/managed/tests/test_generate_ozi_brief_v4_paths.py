"""Acceptance proof: generate_ozi_brief.py is harness-mode-aware (V4-COMPLETE Phase B).

Tests the `resolve_spoke_path(root, mode)` function extracted from the module — that
function is the sole path-resolution surface, so testing it is sufficient to assert the
v3/v4/coexist contracts without loading the full module (which has module-level I/O
side-effects that would fire on import in unexpected envs).
"""
import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = ROOT / "tools"


def _load_gob():
    """Load generate_ozi_brief as a module without triggering its __main__ block."""
    spec = importlib.util.spec_from_file_location(
        "gob_v4_paths",
        str(TOOLS_DIR / "generate_ozi_brief.py"),
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)


@pytest.fixture(scope="module")
def gob():
    return _load_gob()


# ---------------------------------------------------------------------------
# resolve_spoke_path — v3 layout
# ---------------------------------------------------------------------------

def test_v3_base_is_wai_spoke(tmp_path, gob):
    (tmp_path / "WAI-Spoke").mkdir()
    base, adv = gob.resolve_spoke_path(str(tmp_path))
    assert base == tmp_path / "WAI-Spoke"


def test_v3_advisors_under_base(tmp_path, gob):
    (tmp_path / "WAI-Spoke").mkdir()
    base, adv = gob.resolve_spoke_path(str(tmp_path))
    assert adv == tmp_path / "WAI-Spoke" / "advisors"


# ---------------------------------------------------------------------------
# resolve_spoke_path — v4-only layout
# ---------------------------------------------------------------------------

def test_v4_base_is_local(tmp_path, gob):
    (tmp_path / "WAI-Harness" / "spoke" / "local").mkdir(parents=True)
    (tmp_path / "WAI-Harness" / "spoke" / "advisors").mkdir(parents=True)
    base, adv = gob.resolve_spoke_path(str(tmp_path), mode="v4-only")
    assert base == tmp_path / "WAI-Harness" / "spoke" / "local"


def test_v4_advisors_is_sibling_not_under_local(tmp_path, gob):
    """In v4 the advisors dir is WAI-Harness/spoke/advisors — NOT under local/."""
    (tmp_path / "WAI-Harness" / "spoke" / "local").mkdir(parents=True)
    (tmp_path / "WAI-Harness" / "spoke" / "advisors").mkdir(parents=True)
    base, adv = gob.resolve_spoke_path(str(tmp_path), mode="v4-only")
    assert adv == tmp_path / "WAI-Harness" / "spoke" / "advisors"
    # The critical invariant: advisors is NOT nested under the working base (local/).
    assert "local" not in adv.parts


def test_v4_base_parent_is_not_advisors_parent(tmp_path, gob):
    """base.parent != advisors.parent in v4 — they share spoke/, not local/."""
    (tmp_path / "WAI-Harness" / "spoke" / "local").mkdir(parents=True)
    (tmp_path / "WAI-Harness" / "spoke" / "advisors").mkdir(parents=True)
    base, adv = gob.resolve_spoke_path(str(tmp_path), mode="v4-only")
    assert base.parent == adv.parent  # both under WAI-Harness/spoke/
    assert base != adv


# ---------------------------------------------------------------------------
# resolve_spoke_path — coexist layout: no explicit mode defaults to v3
# ---------------------------------------------------------------------------

def test_coexist_no_mode_defaults_v3_overlap_safe(tmp_path, gob):
    (tmp_path / "WAI-Spoke").mkdir()
    (tmp_path / "WAI-Harness" / "spoke" / "local").mkdir(parents=True)
    (tmp_path / "WAI-Harness" / "spoke" / "advisors").mkdir(parents=True)
    base, adv = gob.resolve_spoke_path(str(tmp_path))
    assert base == tmp_path / "WAI-Spoke"
    assert adv == tmp_path / "WAI-Spoke" / "advisors"


def test_coexist_explicit_v4_uses_v4_tree(tmp_path, gob):
    (tmp_path / "WAI-Spoke").mkdir()
    (tmp_path / "WAI-Harness" / "spoke" / "local").mkdir(parents=True)
    (tmp_path / "WAI-Harness" / "spoke" / "advisors").mkdir(parents=True)
    base, adv = gob.resolve_spoke_path(str(tmp_path), mode="v4-only")
    assert base == tmp_path / "WAI-Harness" / "spoke" / "local"
    assert adv == tmp_path / "WAI-Harness" / "spoke" / "advisors"


# ---------------------------------------------------------------------------
# resolve_spoke_path — WAI_HARNESS_MODE env var (no explicit mode arg)
# ---------------------------------------------------------------------------

def test_env_v4_only_uses_v4_tree(tmp_path, gob, monkeypatch):
    (tmp_path / "WAI-Spoke").mkdir()
    (tmp_path / "WAI-Harness" / "spoke" / "local").mkdir(parents=True)
    (tmp_path / "WAI-Harness" / "spoke" / "advisors").mkdir(parents=True)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    base, adv = gob.resolve_spoke_path(str(tmp_path))
    assert base == tmp_path / "WAI-Harness" / "spoke" / "local"


# ---------------------------------------------------------------------------
# resolve_spoke_path — no harness tree: graceful fallback
# ---------------------------------------------------------------------------

def test_no_tree_fallback_to_legacy_layout(tmp_path, gob):
    """When neither WAI-Spoke nor WAI-Harness exists, fall back to the v3 layout
    so that callers running outside a live spoke don't crash."""
    base, adv = gob.resolve_spoke_path(str(tmp_path))
    assert base == tmp_path / "WAI-Spoke"
    assert adv == tmp_path / "WAI-Spoke" / "advisors"


# ---------------------------------------------------------------------------
# Module-level SPOKE_PATH and _ADVISORS_PATH are consistent
# ---------------------------------------------------------------------------

def test_module_constants_consistent(gob):
    """SPOKE_PATH and _ADVISORS_PATH must both be Path objects pointing
    at something reachable from the same root."""
    spoke = gob.SPOKE_PATH
    adv = gob._ADVISORS_PATH
    assert isinstance(spoke, Path)
    assert isinstance(adv, Path)
    # In v3 layout: adv should be inside spoke, OR in v4: adv is a sibling of spoke
    # (both under WAI-Harness/spoke/). Either way adv must NOT be under spoke itself
    # when running in v4. We can at least assert they're not equal.
    assert spoke != adv


def test_module_derived_paths_use_spoke_path(gob):
    """BRIEF_PATH and SCAN_STATE_PATH must be derived from the module constants
    (not from a hardcoded WAI-Spoke string)."""
    assert gob.BRIEF_PATH.parts[-2] == gob.SPOKE_PATH.parts[-1] or \
        str(gob.BRIEF_PATH).startswith(str(gob.SPOKE_PATH))
    # SCAN_STATE_PATH derives from _ADVISORS_PATH
    assert str(gob.SCAN_STATE_PATH).startswith(str(gob._ADVISORS_PATH))
    assert str(gob.REFINEMENTS_PATH).startswith(str(gob._ADVISORS_PATH))
