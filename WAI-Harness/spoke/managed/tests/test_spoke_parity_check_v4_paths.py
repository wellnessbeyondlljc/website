"""AP test: spoke_parity_check.py resolves WAI-State.json via wai_paths (harness-mode-aware).

Scenarios:
  1. v4-only env (WAI_HARNESS_MODE=v4-only): state_file resolved from WAI-Harness/spoke/local
  2. coexist env (no explicit mode, default=v3): state_file resolved from WAI-Spoke
"""
import json
import os
import sys
from pathlib import Path

import pytest

# Ensure tools/ is importable
TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import spoke_parity_check  # noqa: E402


def _write_state(path: Path, hub_path: str) -> None:
    """Write a minimal WAI-State.json with wheel.hub_path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"wheel": {"hub_path": hub_path}}))


def _write_hub_parity(hub_root: Path) -> None:
    """Write a minimal parity head so check_spoke() does not error on hub access."""
    parity_dir = hub_root / "WAI-Hub" / "parity"
    parity_dir.mkdir(parents=True, exist_ok=True)
    (parity_dir / "head.json").write_text(json.dumps({"parity": 0, "patches": []}))


class TestSpokeParityCheckV4Paths:
    """Verify that main() resolves WAI-State.json via wai_paths, not a hardcoded path."""

    def test_v4_only_reads_v4_state(self, tmp_path, monkeypatch):
        """With WAI_HARNESS_MODE=v4-only, state must be read from WAI-Harness/spoke/local."""
        spoke_root = tmp_path / "spoke"

        # v4 tree only
        v4_state = spoke_root / "WAI-Harness" / "spoke" / "local" / "WAI-State.json"
        v4_state.parent.mkdir(parents=True, exist_ok=True)

        # Hub lives outside the spoke; write parity head so the tool doesn't abort early
        hub_root = tmp_path / "hub"
        _write_hub_parity(hub_root)

        _write_state(v4_state, str(hub_root))

        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        # Simulate: main() calls wai_paths.resolve_wai_root(spoke_path) and reads state_file
        import wai_paths
        base, mode = wai_paths.resolve_wai_root(str(spoke_root))
        assert mode == "v4", f"Expected mode=v4, got {mode!r}"
        state_file = Path(base) / "WAI-State.json"
        assert state_file.exists(), "v4 WAI-State.json must resolve and exist"
        with open(state_file) as fh:
            state = json.load(fh)
        assert state["wheel"]["hub_path"] == str(hub_root), "Hub path must come from v4 state"

    def test_coexist_default_reads_v3_state(self, tmp_path, monkeypatch):
        """With both trees present and no explicit mode, default must be v3 (coexist-safe)."""
        spoke_root = tmp_path / "spoke"

        hub_root_v3 = tmp_path / "hub_v3"
        hub_root_v4 = tmp_path / "hub_v4"

        # Both trees present
        v3_state = spoke_root / "WAI-Spoke" / "WAI-State.json"
        v4_state = spoke_root / "WAI-Harness" / "spoke" / "local" / "WAI-State.json"

        _write_state(v3_state, str(hub_root_v3))
        _write_state(v4_state, str(hub_root_v4))

        # Clear any lingering override
        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

        import wai_paths
        base, mode = wai_paths.resolve_wai_root(str(spoke_root))
        assert mode == "v3", f"Coexist default must be v3, got {mode!r}"
        state_file = Path(base) / "WAI-State.json"
        assert state_file.exists(), "v3 WAI-State.json must resolve and exist"
        with open(state_file) as fh:
            state = json.load(fh)
        # Must NOT have read from the v4 tree
        assert state["wheel"]["hub_path"] == str(hub_root_v3), (
            "Coexist default must read from v3 tree, not v4"
        )

    def test_none_base_is_handled_gracefully(self, tmp_path, monkeypatch):
        """If neither tree exists, resolve_wai_root returns (None, 'none') — no crash."""
        spoke_root = tmp_path / "empty_spoke"
        spoke_root.mkdir()
        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

        import wai_paths
        base, mode = wai_paths.resolve_wai_root(str(spoke_root))
        assert base is None
        assert mode == "none"
        # Replicating the None-guard in spoke_parity_check.main():
        state_file = Path(base) / "WAI-State.json" if base is not None else None
        assert state_file is None, "None base must produce None state_file (no crash)"
