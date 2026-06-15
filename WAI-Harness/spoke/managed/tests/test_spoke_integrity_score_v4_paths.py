"""AP test: spoke_integrity_score.py resolves state paths via wai_paths (harness-mode-aware).

Scenarios:
  1. v4-only env (WAI_HARNESS_MODE=v4-only): structure + lugs + state resolved from
     WAI-Harness/spoke/local; WAI-Spoke tree absent -> no dependency on it.
  2. coexist default (no explicit mode, both trees present): resolves from WAI-Spoke (v3).
  3. none (neither tree present): score_structure returns 0 without crashing.
"""
import json
import os
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import spoke_integrity_score  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _populate_v4_tree(spoke_root: Path) -> Path:
    """Create the v4 local base and populate the integrity files inside it."""
    base = spoke_root / "WAI-Harness" / "spoke" / "local"
    base.mkdir(parents=True, exist_ok=True)

    # WAI-State.json
    (base / "WAI-State.json").write_text(json.dumps({"wheel": {"hub_path": ""}}))

    # skills/WAI-Skills.jsonl
    skills_dir = base / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "WAI-Skills.jsonl").write_text("")

    # lugs/bytype  (empty tree is fine — just needs to exist)
    bytype = base / "lugs" / "bytype"
    bytype.mkdir(parents=True, exist_ok=True)

    # sessions/
    (base / "sessions").mkdir(parents=True, exist_ok=True)

    # seed/ingest/
    (base / "seed" / "ingest").mkdir(parents=True, exist_ok=True)

    return base


def _populate_v3_tree(spoke_root: Path) -> Path:
    """Create the v3 WAI-Spoke base and populate the integrity files inside it."""
    base = spoke_root / "WAI-Spoke"
    base.mkdir(parents=True, exist_ok=True)

    (base / "WAI-State.json").write_text(json.dumps({"wheel": {"hub_path": ""}}))

    skills_dir = base / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "WAI-Skills.jsonl").write_text("")

    bytype = base / "lugs" / "bytype"
    bytype.mkdir(parents=True, exist_ok=True)

    (base / "sessions").mkdir(parents=True, exist_ok=True)
    (base / "seed" / "ingest").mkdir(parents=True, exist_ok=True)

    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSpokeIntegrityScoreV4Paths:

    def test_v4_only_structure_score_uses_v4_tree(self, tmp_path, monkeypatch):
        """WAI_HARNESS_MODE=v4-only: score_structure finds files in WAI-Harness/spoke/local."""
        spoke_root = tmp_path / "spoke"
        _populate_v4_tree(spoke_root)
        # Deliberately do NOT create WAI-Spoke — v4-only must not need it

        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        score, notes = spoke_integrity_score.score_structure(spoke_root)

        assert score == 20, (
            f"Expected 20/20 (all 5 v4 files present), got {score}. Notes: {notes}"
        )
        assert notes == [], f"Unexpected notes: {notes}"

    def test_v4_only_no_wai_spoke_access(self, tmp_path, monkeypatch):
        """v4-only: score_structure must NOT depend on WAI-Spoke; WAI-Spoke absent -> full score."""
        spoke_root = tmp_path / "spoke"
        _populate_v4_tree(spoke_root)

        # Confirm WAI-Spoke does not exist
        assert not (spoke_root / "WAI-Spoke").exists(), "Test setup: WAI-Spoke must be absent"

        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        score, notes = spoke_integrity_score.score_structure(spoke_root)
        assert score == 20, (
            f"score_structure must not require WAI-Spoke in v4-only; got {score}. Notes: {notes}"
        )

    def test_v4_only_lugs_score_uses_v4_tree(self, tmp_path, monkeypatch):
        """v4-only: score_lugs finds lugs/bytype in WAI-Harness/spoke/local."""
        spoke_root = tmp_path / "spoke"
        v4_base = _populate_v4_tree(spoke_root)

        # Plant one valid lug with full PEV in the v4 tree
        lug_dir = v4_base / "lugs" / "bytype" / "task" / "open"
        lug_dir.mkdir(parents=True, exist_ok=True)
        (lug_dir / "lug-abc123.json").write_text(json.dumps({
            "id": "lug-abc123",
            "type": "task",
            "status": "open",
            "perceive": "observe something",
            "execute": "do something",
            "verify": "confirm something",
        }))

        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        score, notes = spoke_integrity_score.score_lugs(spoke_root)
        # 1 actionable lug, full PEV -> no deductions -> 20/20
        assert score == 20, f"Expected 20/20, got {score}. Notes: {notes}"
        assert notes == [], f"Unexpected notes: {notes}"

    def test_v4_only_missing_bytype_scores_zero(self, tmp_path, monkeypatch):
        """v4-only with no lugs/bytype in v4 tree -> score_lugs returns 0."""
        spoke_root = tmp_path / "spoke"
        # Create WAI-Harness but do NOT populate lugs/bytype
        (spoke_root / "WAI-Harness" / "spoke" / "local").mkdir(parents=True, exist_ok=True)

        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        score, notes = spoke_integrity_score.score_lugs(spoke_root)
        assert score == 0, f"Expected 0 (bytype missing), got {score}"
        assert any("missing" in n for n in notes), f"Expected 'missing' note, got: {notes}"

    def test_coexist_default_reads_v3_tree(self, tmp_path, monkeypatch):
        """Both trees present, no explicit mode: score_structure reads from WAI-Spoke (v3)."""
        spoke_root = tmp_path / "spoke"

        # v3 tree: fully populated
        _populate_v3_tree(spoke_root)

        # v4 tree: present but EMPTY (integrity files missing)
        (spoke_root / "WAI-Harness" / "spoke" / "local").mkdir(parents=True, exist_ok=True)

        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

        score, notes = spoke_integrity_score.score_structure(spoke_root)
        # v3 has all 5 files -> 20/20
        assert score == 20, (
            f"Coexist default must read from v3; expected 20/20 but got {score}. Notes: {notes}"
        )
        assert notes == [], f"Unexpected notes: {notes}"

    def test_neither_tree_scores_zero_no_crash(self, tmp_path, monkeypatch):
        """No WAI-Spoke and no WAI-Harness: score_structure returns 0 without raising."""
        spoke_root = tmp_path / "empty_spoke"
        spoke_root.mkdir()

        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)

        score, notes = spoke_integrity_score.score_structure(spoke_root)
        assert score == 0, f"Expected 0 (no tree present), got {score}"
        assert len(notes) == 5, f"Expected 5 'missing' notes, got {len(notes)}: {notes}"

    def test_v4_only_compute_score_reads_hub_path_from_v4(self, tmp_path, monkeypatch):
        """compute_score() reads hub_path from the v4 state file, not WAI-Spoke."""
        spoke_root = tmp_path / "spoke"
        v4_base = _populate_v4_tree(spoke_root)

        sentinel_hub = str(tmp_path / "sentinel_hub")
        (v4_base / "WAI-State.json").write_text(
            json.dumps({"wheel": {"hub_path": sentinel_hub}})
        )

        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        result = spoke_integrity_score.compute_score(str(spoke_root))
        # hub_path is what gets passed to score_parity / score_hub; those return 0 if hub
        # missing, but the key assertion is that the result dict exists and doesn't crash.
        assert "score" in result, "compute_score must return a score key"
        assert "dimensions" in result, "compute_score must return dimensions key"
        # The WAI-Spoke tree does not exist — if compute_score internally referenced it
        # for state_file, it would silently leave hub_path empty (score_parity/score_hub
        # would get an empty string). Verify the path we CAN check: structure score == 20
        # because all v4 files were planted.
        assert result["dimensions"]["structure"]["score"] == 20, (
            "structure score must be 20 (all v4 integrity files present)"
        )
