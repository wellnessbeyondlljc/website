"""Acceptance proof: advisor_schedule_eval.py is harness-mode aware.

Tests:
  1. v4-only ($WAI_HARNESS_MODE=v4-only): _resolve_paths returns paths under
     WAI-Harness/spoke/local (base) and WAI-Harness/spoke/advisors (sibling).
     Zero WAI-Spoke access.
  2. coexist with no explicit mode: _resolve_paths returns v3 (WAI-Spoke) paths
     (overlap-safe default: v3 wins when both trees present).
  3. v3-only: _resolve_paths returns WAI-Spoke paths.
  4. load_spoke_state reads from the v4 WAI-State.json in v4-only mode.
  5. _resolve_paths returned paths never contain "WAI-Spoke" string in v4-only mode.
"""
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_ase(monkeypatch_env=None):
    """Load advisor_schedule_eval as a fresh module (bypasses import cache).

    monkeypatch_env: dict of env-var overrides applied before loading; cleared
    after load so callers can set WAI_HARNESS_MODE per test.
    """
    # We reload by re-execing the spec so each test gets a clean module state
    # (the module-level _wai_paths import is otherwise cached).
    spec = importlib.util.spec_from_file_location(
        "ase_v4_paths_test",
        os.path.join(str(ROOT), "tools", "advisor_schedule_eval.py"),
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _make_v3_tree(tmp_path: Path) -> Path:
    """Create a minimal v3 spoke tree under tmp_path."""
    base = tmp_path / "WAI-Spoke"
    base.mkdir(parents=True)
    advisors = base / "advisors"
    advisors.mkdir()
    (advisors / "schedule-index.json").write_text(json.dumps([]))
    (base / "WAI-State.json").write_text(json.dumps({"_v": "v3"}))
    (advisors / "tool-advisor").mkdir()
    (advisors / "tool-advisor" / "scan_state.json").write_text(json.dumps({}))
    return tmp_path


def _make_v4_tree(tmp_path: Path) -> Path:
    """Create a minimal v4 spoke tree under tmp_path."""
    local = tmp_path / "WAI-Harness" / "spoke" / "local"
    local.mkdir(parents=True)
    advisors = tmp_path / "WAI-Harness" / "spoke" / "advisors"
    advisors.mkdir(parents=True)
    (advisors / "schedule-index.json").write_text(json.dumps([]))
    (local / "WAI-State.json").write_text(json.dumps({"_v": "v4"}))
    (advisors / "tool-advisor").mkdir()
    (advisors / "tool-advisor" / "scan_state.json").write_text(json.dumps({}))
    return tmp_path


def _make_coexist_tree(tmp_path: Path) -> Path:
    """Both v3 and v4 trees present."""
    _make_v3_tree(tmp_path)
    _make_v4_tree(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Test 1: v4-only mode → all paths in v4 tree
# ---------------------------------------------------------------------------

def test_v4only_schedule_index_in_v4_tree(tmp_path, monkeypatch):
    """In v4-only mode, schedule_index path must be under WAI-Harness/spoke/advisors."""
    _make_v4_tree(tmp_path)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    ase = _load_ase()

    paths = ase._resolve_paths(str(tmp_path))
    expected = str(tmp_path / "WAI-Harness" / "spoke" / "advisors" / "schedule-index.json")
    assert paths["schedule_index"] == expected, (
        f"Expected v4 schedule_index path, got: {paths['schedule_index']}"
    )


def test_v4only_wai_state_in_v4_tree(tmp_path, monkeypatch):
    """In v4-only mode, wai_state path must be under WAI-Harness/spoke/local."""
    _make_v4_tree(tmp_path)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    ase = _load_ase()

    paths = ase._resolve_paths(str(tmp_path))
    expected = str(tmp_path / "WAI-Harness" / "spoke" / "local" / "WAI-State.json")
    assert paths["wai_state"] == expected, (
        f"Expected v4 wai_state path, got: {paths['wai_state']}"
    )


def test_v4only_tool_advisor_state_in_v4_tree(tmp_path, monkeypatch):
    """In v4-only mode, tool_advisor_state must be under WAI-Harness/spoke/advisors."""
    _make_v4_tree(tmp_path)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    ase = _load_ase()

    paths = ase._resolve_paths(str(tmp_path))
    expected = str(tmp_path / "WAI-Harness" / "spoke" / "advisors" / "tool-advisor" / "scan_state.json")
    assert paths["tool_advisor_state"] == expected, (
        f"Expected v4 tool_advisor_state path, got: {paths['tool_advisor_state']}"
    )


def test_v4only_db_supabase_in_v4_tree(tmp_path, monkeypatch):
    """In v4-only mode, db_supabase must be under WAI-Harness/spoke/local."""
    _make_v4_tree(tmp_path)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    ase = _load_ase()

    paths = ase._resolve_paths(str(tmp_path))
    expected = str(tmp_path / "WAI-Harness" / "spoke" / "local" / "db" / "supabase")
    assert paths["db_supabase"] == expected, (
        f"Expected v4 db_supabase path, got: {paths['db_supabase']}"
    )


def test_v4only_vendors_in_v4_tree(tmp_path, monkeypatch):
    """In v4-only mode, vendors path must be under WAI-Harness/spoke/local."""
    _make_v4_tree(tmp_path)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    ase = _load_ase()

    paths = ase._resolve_paths(str(tmp_path))
    expected = str(tmp_path / "WAI-Harness" / "spoke" / "local" / "vendors.json")
    assert paths["vendors"] == expected, (
        f"Expected v4 vendors path, got: {paths['vendors']}"
    )


def test_v4only_no_wai_spoke_in_any_path(tmp_path, monkeypatch):
    """Zero WAI-Spoke strings in any resolved path in v4-only mode."""
    _make_v4_tree(tmp_path)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    ase = _load_ase()

    paths = ase._resolve_paths(str(tmp_path))
    for key, val in paths.items():
        if val is None:
            continue
        assert "WAI-Spoke" not in str(val), (
            f"Key '{key}' contains WAI-Spoke in v4-only mode: {val}"
        )


# ---------------------------------------------------------------------------
# Test 2: coexist (no explicit mode) → v3 paths (overlap-safe default)
# ---------------------------------------------------------------------------

def test_coexist_no_mode_resolves_v3(tmp_path, monkeypatch):
    """Coexist with no explicit WAI_HARNESS_MODE defaults to v3 paths."""
    _make_coexist_tree(tmp_path)
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
    ase = _load_ase()

    paths = ase._resolve_paths(str(tmp_path))
    assert "WAI-Spoke" in paths["schedule_index"], (
        f"Coexist+no-mode should resolve to v3; got: {paths['schedule_index']}"
    )
    assert "WAI-Spoke" in paths["wai_state"], (
        f"Coexist+no-mode wai_state should be v3; got: {paths['wai_state']}"
    )
    assert "WAI-Harness" not in paths["schedule_index"]
    assert "WAI-Harness" not in paths["wai_state"]


# ---------------------------------------------------------------------------
# Test 3: v3-only tree → v3 paths regardless of env
# ---------------------------------------------------------------------------

def test_v3only_tree_resolves_v3(tmp_path, monkeypatch):
    """v3-only tree (no WAI-Harness) resolves v3 paths."""
    _make_v3_tree(tmp_path)
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
    ase = _load_ase()

    paths = ase._resolve_paths(str(tmp_path))
    expected_si = str(tmp_path / "WAI-Spoke" / "advisors" / "schedule-index.json")
    assert paths["schedule_index"] == expected_si
    expected_ws = str(tmp_path / "WAI-Spoke" / "WAI-State.json")
    assert paths["wai_state"] == expected_ws


# ---------------------------------------------------------------------------
# Test 4: load_spoke_state reads v4 WAI-State.json in v4-only mode
# ---------------------------------------------------------------------------

def test_load_spoke_state_reads_v4(tmp_path, monkeypatch):
    """load_spoke_state returns data from v4 WAI-State.json in v4-only mode."""
    root = _make_v4_tree(tmp_path)
    # Write a distinctive sentinel value into the v4 WAI-State.json
    v4_state_path = root / "WAI-Harness" / "spoke" / "local" / "WAI-State.json"
    v4_state_path.write_text(json.dumps({"_v": "v4", "sentinel": "v4-state"}))

    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    ase = _load_ase()

    state = ase.load_spoke_state(str(root))
    assert state.get("sentinel") == "v4-state", (
        f"Expected v4 state sentinel, got: {state}"
    )


def test_load_spoke_state_reads_v3_in_coexist(tmp_path, monkeypatch):
    """load_spoke_state reads from v3 WAI-State.json in coexist (no mode) default."""
    root = _make_coexist_tree(tmp_path)
    v3_state_path = root / "WAI-Spoke" / "WAI-State.json"
    v3_state_path.write_text(json.dumps({"_v": "v3", "sentinel": "v3-state"}))

    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
    ase = _load_ase()

    state = ase.load_spoke_state(str(root))
    assert state.get("sentinel") == "v3-state", (
        f"Expected v3 state sentinel, got: {state}"
    )


# ---------------------------------------------------------------------------
# Test 5: advisors dir is the sibling (not under local) in v4-only
# ---------------------------------------------------------------------------

def test_v4only_advisors_is_sibling_not_under_local(tmp_path, monkeypatch):
    """v4 advisors dir is WAI-Harness/spoke/advisors, NOT WAI-Harness/spoke/local/advisors."""
    _make_v4_tree(tmp_path)
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    ase = _load_ase()

    paths = ase._resolve_paths(str(tmp_path))
    si = paths["schedule_index"]
    # Must be under .../spoke/advisors/
    assert "/spoke/advisors/" in si, (
        f"schedule_index should be under spoke/advisors (sibling), got: {si}"
    )
    # Must NOT be under .../spoke/local/advisors/
    assert "/spoke/local/advisors/" not in si, (
        f"schedule_index must NOT be under local/advisors (v3 pattern), got: {si}"
    )
