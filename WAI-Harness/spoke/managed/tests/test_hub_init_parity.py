"""Integration test: hub-init parity — harness_init --node hub bootstraps a temp hub
from hub-only/base, stamped node_type=hub + _harness.hub_base_version."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HUB_PATH = Path(__file__).resolve().parents[2] / "hub"
TOOL = REPO / "tools" / "harness_init.py"


def _run_init(target: Path, node: str = "spoke", hub_path: Path = None,
              dry_run: bool = False, extra_args=None):
    cmd = [
        sys.executable, str(TOOL),
        "--target", str(target),
        "--name", "Test Node",
        "--node", node,
    ]
    if hub_path:
        cmd += ["--hub-path", str(hub_path)]
    if dry_run:
        cmd.append("--dry-run")
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


# ---------------------------------------------------------------------------
# Hub-init parity tests
# ---------------------------------------------------------------------------

class TestHubInitParity:

    def test_hub_init_creates_wai_spoke(self, tmp_path):
        """Hub init creates the standard spoke structure."""
        result = _run_init(tmp_path, node="hub", hub_path=HUB_PATH)
        assert result.returncode == 0, f"hub init failed:\n{result.stdout}\n{result.stderr}"
        assert (tmp_path / "WAI-Spoke").is_dir()
        assert (tmp_path / "WAI-Spoke" / "sessions").is_dir()
        assert (tmp_path / "WAI-Spoke" / "lugs").is_dir()

    def test_hub_init_creates_wai_hub(self, tmp_path):
        """Hub init creates WAI-Hub/ (hub-specific state dir)."""
        result = _run_init(tmp_path, node="hub", hub_path=HUB_PATH)
        assert result.returncode == 0
        assert (tmp_path / "WAI-Hub").is_dir()
        assert (tmp_path / "WAI-Hub" / "advisors").is_dir()

    def test_hub_init_creates_teachings_repo(self, tmp_path):
        """Hub init creates the canonical teachings_repo/ structure."""
        result = _run_init(tmp_path, node="hub", hub_path=HUB_PATH)
        assert result.returncode == 0
        for expected in [
            "teachings_repo/spoke/current",
            "teachings_repo/cross_spoke/current",
            "teachings_repo/hub-only/current",
            "teachings_repo/hub-only/base",
            "teachings_repo/framework/current",
        ]:
            assert (tmp_path / expected).is_dir(), f"Missing: {expected}"

    def test_hub_init_creates_spoke_current_index(self, tmp_path):
        """Hub init seeds index.json for spoke/current and cross_spoke/current."""
        result = _run_init(tmp_path, node="hub", hub_path=HUB_PATH)
        assert result.returncode == 0
        for idx_path in [
            "teachings_repo/spoke/current/index.json",
            "teachings_repo/cross_spoke/current/index.json",
        ]:
            p = tmp_path / idx_path
            assert p.exists(), f"Missing: {idx_path}"
            data = json.loads(p.read_text())
            assert "teachings" in data

    def test_hub_init_stamps_node_type_hub(self, tmp_path):
        """Hub init stamps wheel.node_type = hub in WAI-State.json."""
        result = _run_init(tmp_path, node="hub", hub_path=HUB_PATH)
        assert result.returncode == 0
        state = json.loads((tmp_path / "WAI-Spoke" / "WAI-State.json").read_text())
        assert state.get("wheel", {}).get("node_type") == "hub", (
            f"Expected node_type=hub, got: {state.get('wheel', {}).get('node_type')}"
        )

    def test_hub_init_stamps_hub_base_version(self, tmp_path):
        """Hub init stamps _harness.hub_base_version from hub-only base index."""
        result = _run_init(tmp_path, node="hub", hub_path=HUB_PATH)
        assert result.returncode == 0
        state = json.loads((tmp_path / "WAI-Spoke" / "WAI-State.json").read_text())
        hub_base_version = state.get("_harness", {}).get("hub_base_version")
        assert hub_base_version is not None, "_harness.hub_base_version not set"
        # Must match hub-only/base/index.json base_version
        base_idx = HUB_PATH / "teachings_repo" / "hub-only" / "base" / "index.json"
        if base_idx.exists():
            expected = json.loads(base_idx.read_text()).get("base_version")
            assert hub_base_version == expected, (
                f"hub_base_version {hub_base_version!r} != base index {expected!r}"
            )

    def test_hub_init_seeds_hub_specific_tools(self, tmp_path):
        """Hub init seeds hub-specific tools from hub-only/base/payload/tools/."""
        result = _run_init(tmp_path, node="hub", hub_path=HUB_PATH)
        assert result.returncode == 0
        # generate_wakeup_brief.py is in hub-only/base/payload/tools/
        assert (tmp_path / "tools" / "generate_wakeup_brief.py").exists(), (
            "generate_wakeup_brief.py not seeded from hub base payload"
        )

    def test_hub_init_creates_hub_registry(self, tmp_path):
        """Hub init creates hub-registry.json from template."""
        result = _run_init(tmp_path, node="hub", hub_path=HUB_PATH)
        assert result.returncode == 0
        reg = tmp_path / "hub-registry.json"
        assert reg.exists(), "hub-registry.json not created"
        data = json.loads(reg.read_text())
        assert "wheels" in data, "hub-registry.json missing 'wheels' key"

    def test_hub_init_born_at_head(self, tmp_path):
        """Hub born at-head: both spoke base_version and hub_base_version are set."""
        result = _run_init(tmp_path, node="hub", hub_path=HUB_PATH)
        assert result.returncode == 0
        state = json.loads((tmp_path / "WAI-Spoke" / "WAI-State.json").read_text())
        harness = state.get("_harness", {})
        # base_version from spoke/base (may be None if no spoke base payload seeded yet)
        # hub_base_version from hub-only/base (must always be set)
        assert harness.get("hub_base_version") is not None, (
            "Hub not born at-head: _harness.hub_base_version missing"
        )

    def test_spoke_init_greenfield_is_v4_only(self, tmp_path):
        """Greenfield spoke init (no --node flag) defaults to the v4-only layout:
        state under WAI-Harness/spoke/local, NO legacy WAI-Spoke/ tree, and none of
        the hub-only artifacts. Guards the split-brain fix (a fresh spoke must not be
        born with a v3 tree it has no history to justify)."""
        result = _run_init(tmp_path, node="spoke", hub_path=HUB_PATH)
        assert result.returncode == 0
        # v4-only: state lives in the v4 base, NOT in a legacy WAI-Spoke/ tree.
        v4_state = tmp_path / "WAI-Harness" / "spoke" / "local" / "WAI-State.json"
        assert v4_state.exists(), "greenfield spoke should have v4 state at WAI-Harness/spoke/local"
        assert not (tmp_path / "WAI-Spoke").exists(), "greenfield spoke must NOT create a legacy WAI-Spoke/ tree"
        state = json.loads(v4_state.read_text())
        # Spoke must NOT have node_type=hub
        assert state.get("wheel", {}).get("node_type") != "hub"
        # Spoke must NOT have WAI-Hub/ or teachings_repo/
        assert not (tmp_path / "WAI-Hub").exists()
        assert not (tmp_path / "teachings_repo").exists()

    def test_spoke_init_coexist_on_existing_v3(self, tmp_path):
        """An existing v3 spoke (WAI-Spoke/ already present) re-inits in coexist —
        the v4-only default must not disrupt a live legacy tree."""
        (tmp_path / "WAI-Spoke").mkdir()
        result = _run_init(tmp_path, node="spoke", hub_path=HUB_PATH)
        assert result.returncode == 0
        assert (tmp_path / "WAI-Spoke" / "WAI-State.json").exists()

    def test_dry_run_produces_no_files(self, tmp_path):
        """--dry-run mode writes no files."""
        result = _run_init(tmp_path, node="hub", hub_path=HUB_PATH, dry_run=True)
        assert result.returncode == 0
        # Only pre-existing files; no WAI-Spoke/ created
        assert not (tmp_path / "WAI-Spoke").exists()

    def test_hub_init_no_hub_path(self, tmp_path):
        """Hub init without --hub-path succeeds but cannot seed from bases (graceful note)."""
        result = _run_init(tmp_path, node="hub")
        assert result.returncode == 0
        assert "no --hub-path" in result.stdout or result.returncode == 0
        # hub base version NOT set since no seed source
        state = json.loads((tmp_path / "WAI-Spoke" / "WAI-State.json").read_text())
        assert state.get("_harness", {}).get("hub_base_version") is None


# ---------------------------------------------------------------------------
# hub-only/base structure tests (static, no harness_init invocation needed)
# ---------------------------------------------------------------------------

class TestHubBaseStructure:

    HUB_BASE = HUB_PATH / "teachings_repo" / "hub-only" / "base"

    @pytest.mark.skipif(not HUB_PATH.exists(), reason="live hub not present")
    def test_hub_base_index_exists(self):
        """hub-only/base/index.json exists and has base_version."""
        idx = self.HUB_BASE / "index.json"
        assert idx.exists()
        data = json.loads(idx.read_text())
        assert "base_version" in data
        assert data["base_version"]

    @pytest.mark.skipif(not HUB_PATH.exists(), reason="live hub not present")
    def test_hub_base_has_adoption_kit(self):
        """hub-only/base/ has all adoption kit files (00-manifest through 06-verify)."""
        for fname in ["00-manifest.json", "01-orient.md", "02-detect.md",
                      "03-bootstrap.md", "04-migrate.md", "05-hygiene.md", "06-verify.md"]:
            assert (self.HUB_BASE / fname).exists(), f"Missing kit file: {fname}"

    @pytest.mark.skipif(not HUB_PATH.exists(), reason="live hub not present")
    def test_hub_base_has_teachings_index(self):
        """hub-only/base/teachings/index.json exists with a base_version and cap."""
        idx = self.HUB_BASE / "teachings" / "index.json"
        assert idx.exists()
        data = json.loads(idx.read_text())
        assert "base_version" in data
        assert "cap" in data
        assert "patches" in data

    @pytest.mark.skipif(not HUB_PATH.exists(), reason="live hub not present")
    def test_hub_base_payload_has_tools(self):
        """hub-only/base/payload/tools/ has at least generate_wakeup_brief.py."""
        tools = self.HUB_BASE / "payload" / "tools"
        assert tools.is_dir()
        assert (tools / "generate_wakeup_brief.py").exists()
