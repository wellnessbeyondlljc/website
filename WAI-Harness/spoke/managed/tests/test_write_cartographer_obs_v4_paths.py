"""test_write_cartographer_obs_v4_paths.py

AP test: write_cartographer_obs resolves its observations / state / lugs paths
through wai_paths (harness-mode-aware) instead of the old bare cwd-relative
"WAI-Spoke/..." strings that no-op on a v4-only spoke.

Invariants:
  1. WAI_HARNESS_MODE=v4-only on a v4 fixture -> observations dir, WAI-State.json
     and the lug glob all resolve under WAI-Harness/spoke/local with NO
     "WAI-Spoke" segment (cartographer is built off the resolved working base;
     WAI-State.json and lugs are wai_paths categories).
  2. v3 fixture (explicit v3-only) -> all three resolve under WAI-Spoke
     (legacy semantics preserved as a guarded fallback only).

Importing the module must be side-effect free (no file I/O at import) — proven
implicitly by the bare `import write_cartographer_obs` below not raising.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import write_cartographer_obs  # noqa: E402 — must come after sys.path insert


def _make_v4_tree(spoke_root):
    # local/WAI-State.json marker => v4-activated; WAI-Harness present => has_v4
    os.makedirs(os.path.join(spoke_root, "WAI-Harness", "spoke", "local"), exist_ok=True)


def _make_v3_tree(spoke_root):
    os.makedirs(os.path.join(spoke_root, "WAI-Spoke"), exist_ok=True)


class TestV4OnlyMode:
    def test_paths_target_v4_local(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        _make_v4_tree(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        obs_dir, state_file, lugs_glob = write_cartographer_obs._resolve_paths(tmp)
        v4_base = os.path.join("WAI-Harness", "spoke", "local")

        for label, p in (("obs_dir", obs_dir), ("state_file", state_file), ("lugs_glob", lugs_glob)):
            assert v4_base in p, f"{label} not under v4 local base: {p}"
            assert "WAI-Spoke" not in p, f"{label} still references legacy WAI-Spoke: {p}"

        assert obs_dir.endswith(os.path.join("cartographer", "observations"))
        assert state_file.endswith("WAI-State.json")
        assert lugs_glob.endswith(os.path.join("lugs", "bytype", "*", "in_progress", "*.json"))


class TestV3OnlyMode:
    def test_paths_target_v3_wai_spoke(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        _make_v3_tree(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v3-only")

        obs_dir, state_file, lugs_glob = write_cartographer_obs._resolve_paths(tmp)

        for label, p in (("obs_dir", obs_dir), ("state_file", state_file), ("lugs_glob", lugs_glob)):
            assert "WAI-Spoke" in p, f"{label} not under v3 WAI-Spoke: {p}"
            assert os.path.join("WAI-Harness", "spoke", "local") not in p

        assert obs_dir.endswith(os.path.join("WAI-Spoke", "cartographer", "observations"))
        assert state_file.endswith(os.path.join("WAI-Spoke", "WAI-State.json"))
        assert os.path.join("WAI-Spoke", "lugs", "bytype") in lugs_glob


class TestGuardedFallback:
    def test_no_tree_falls_back_to_v3_layout(self, monkeypatch, tmp_path):
        # Neither tree present: resolve_wai_root returns None -> guarded v3 fallback.
        tmp = str(tmp_path)
        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

        obs_dir, state_file, lugs_glob = write_cartographer_obs._resolve_paths(tmp)

        assert obs_dir.endswith(os.path.join("WAI-Spoke", "cartographer", "observations"))
        assert state_file.endswith(os.path.join("WAI-Spoke", "WAI-State.json"))
        assert os.path.join("WAI-Spoke", "lugs", "bytype") in lugs_glob
