"""test_burn_panel_v4_paths.py

AP test: burn_panel resolves its sessions / lugs / usage paths through wai_paths
(harness-mode-aware) instead of the old orphan managed/WAI-Spoke constants.

Invariants:
  1. WAI_HARNESS_MODE=v4-only on a v4 fixture -> sessions, lugs(bytype) and the
     usage file all resolve under WAI-Harness/spoke/local with NO "WAI-Spoke"
     segment (proving it no longer points at the phantom managed/WAI-Spoke tree).
  2. v3 fixture (explicit v3-only) -> all three resolve under WAI-Spoke
     (legacy semantics preserved as a guarded fallback).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import burn_panel  # noqa: E402 — must come after sys.path insert


def _make_v4_tree(spoke_root):
    # local/ marker => v4-activated; WAI-Harness present => has_v4
    os.makedirs(os.path.join(spoke_root, "WAI-Harness", "spoke", "local"), exist_ok=True)


def _make_v3_tree(spoke_root):
    os.makedirs(os.path.join(spoke_root, "WAI-Spoke"), exist_ok=True)


class TestV4OnlyMode:
    def test_paths_target_v4_local(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        _make_v4_tree(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        paths = burn_panel._resolve_paths(tmp)
        v4_base = os.path.join("WAI-Harness", "spoke", "local")

        for key in ("SESSIONS_DIR", "LUGS_BYTYPE", "USAGE_FILE"):
            p = paths[key]
            assert v4_base in p, f"{key} not under v4 local base: {p}"
            assert "WAI-Spoke" not in p, f"{key} still references phantom WAI-Spoke: {p}"

        assert paths["SESSIONS_DIR"].endswith(os.path.join("local", "sessions"))
        assert paths["LUGS_BYTYPE"].endswith(os.path.join("lugs", "bytype"))
        assert paths["USAGE_FILE"].endswith(os.path.join("model-usage", "usage.jsonl"))


class TestV3OnlyMode:
    def test_paths_target_v3(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        _make_v3_tree(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v3-only")

        paths = burn_panel._resolve_paths(tmp)

        for key in ("SESSIONS_DIR", "LUGS_BYTYPE", "USAGE_FILE"):
            assert "WAI-Spoke" in paths[key], f"{key} not under v3 base: {paths[key]}"

        assert paths["SESSIONS_DIR"].endswith(os.path.join("WAI-Spoke", "sessions"))
        assert paths["LUGS_BYTYPE"].endswith(os.path.join("lugs", "bytype"))
        assert paths["USAGE_FILE"].endswith(os.path.join("model-usage", "usage.jsonl"))
