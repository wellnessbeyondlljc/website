"""Acceptance proof: wai_paths.py — harness-mode WAI root resolver (V4-COMPLETE Phase B keystone).

The resolver is the single source of truth that lets a WAI_HARNESS_MODE=v4-only session
run entirely on WAI-Harness/spoke/local with zero WAI-Spoke dependency. These tests use
isolated temp trees so they assert the contract, not the live framework layout.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import wai_paths as W  # noqa: E402


def _mk(tmp_path, v3=False, v4=False):
    if v3:
        (tmp_path / "WAI-Spoke").mkdir()
    if v4:
        (tmp_path / "WAI-Harness" / "spoke" / "local").mkdir(parents=True)
        (tmp_path / "WAI-Harness" / "spoke" / "advisors").mkdir(parents=True)
    return str(tmp_path)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)


# --- auto-detection (no explicit mode, no env) -------------------------------

def test_coexist_defaults_v3_overlap_safe(tmp_path):
    # OVERLAP SAFETY: when both trees exist and no mode is requested, default to v3 —
    # the legacy tree every live reader still consumes. v4 must be an explicit opt-in.
    root = _mk(tmp_path, v3=True, v4=True)
    base, mode = W.resolve_wai_root(root)
    assert mode == "v3"
    assert base.endswith("WAI-Spoke")


def test_only_v4_tree_resolves_v4(tmp_path):
    # END STATE: WAI-Spoke gone, only WAI-Harness present -> v4 with no env needed.
    root = _mk(tmp_path, v3=False, v4=True)
    base, mode = W.resolve_wai_root(root)
    assert mode == "v4"
    assert base.endswith(os.path.join("WAI-Harness", "spoke", "local"))


def test_v3_only_tree_resolves_v3(tmp_path):
    root = _mk(tmp_path, v3=True, v4=False)
    base, mode = W.resolve_wai_root(root)
    assert mode == "v3"
    assert base.endswith("WAI-Spoke")


def test_no_tree_resolves_none(tmp_path):
    root = _mk(tmp_path)
    base, mode = W.resolve_wai_root(root)
    assert mode == "none" and base is None


# --- explicit mode arg wins, token variants all accepted ---------------------

@pytest.mark.parametrize("token", ["v4", "v4-only", "v4only", "V4-ONLY"])
def test_v4_tokens_force_v4(tmp_path, token):
    root = _mk(tmp_path, v3=True, v4=True)
    _, mode = W.resolve_wai_root(root, token)
    assert mode == "v4"


@pytest.mark.parametrize("token", ["v3", "v3-only", "v3only"])
def test_v3_tokens_force_v3_when_present(tmp_path, token):
    root = _mk(tmp_path, v3=True, v4=True)
    base, mode = W.resolve_wai_root(root, token)
    assert mode == "v3" and base.endswith("WAI-Spoke")


def test_explicit_v4_without_v4_tree_falls_through(tmp_path):
    # asked for v4 but only v3 exists -> auto fallback to v3 (mirrors harness_mode.sh)
    root = _mk(tmp_path, v3=True, v4=False)
    _, mode = W.resolve_wai_root(root, "v4-only")
    assert mode == "v3"


# --- env override honoured when no arg ---------------------------------------

def test_env_override(tmp_path, monkeypatch):
    root = _mk(tmp_path, v3=True, v4=True)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v3-only")
    _, mode = W.resolve_wai_root(root)
    assert mode == "v3"


def test_arg_beats_env(tmp_path, monkeypatch):
    root = _mk(tmp_path, v3=True, v4=True)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v3-only")
    _, mode = W.resolve_wai_root(root, "v4-only")
    assert mode == "v4"


# --- category mapping, incl. the advisors sibling case -----------------------

def test_local_category_under_base(tmp_path):
    root = _mk(tmp_path, v4=True)
    assert W.category(root, "savepoints", "v4-only").endswith(
        os.path.join("WAI-Harness", "spoke", "local", "savepoints"))


def test_advisors_is_sibling_not_under_local(tmp_path):
    root = _mk(tmp_path, v4=True)
    adv = W.category(root, "advisors", "v4-only")
    assert adv.endswith(os.path.join("WAI-Harness", "spoke", "advisors"))
    assert "local" not in Path(adv).parts  # the whole point: NOT under local/


def test_advisors_v3(tmp_path):
    root = _mk(tmp_path, v3=True)
    assert W.category(root, "advisors", "v3-only").endswith(
        os.path.join("WAI-Spoke", "advisors"))


def test_wai_paths_map_complete(tmp_path):
    root = _mk(tmp_path, v4=True)
    p = W.wai_paths(root, "v4-only")
    assert p["_mode"] == "v4"
    for name in W.LOCAL_CATEGORIES:
        assert p[name].endswith(os.path.join("spoke", "local", name))
    assert p["advisors"].endswith(os.path.join("spoke", "advisors"))


def test_wai_paths_none_when_no_tree(tmp_path):
    root = _mk(tmp_path)
    assert W.wai_paths(root) == {"_mode": "none", "_base": None}


# --- the native proof: v4-only never resolves into WAI-Spoke -----------------

def test_v4_only_never_touches_wai_spoke(tmp_path):
    root = _mk(tmp_path, v3=True, v4=True)
    p = W.wai_paths(root, "v4-only")
    for k, v in p.items():
        if isinstance(v, str) and v:
            assert "WAI-Spoke" not in v, f"{k} leaked into WAI-Spoke: {v}"
