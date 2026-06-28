"""Acceptance proof: P2 v3-noop sweep (impl-fix-p2-v3noop-sweep-v1).

A cluster of managed tools hardcoded `WAI-Spoke/` as their SOLE path, so on a v4-only
spoke they ran but silently no-op'd (read/wrote a phantom tree). The sweep routes each
through wai_paths. These tests assert that on an isolated v4 fixture every swept tool
resolves its base to WAI-Harness/spoke/local (or the advisors sibling), never WAI-Spoke.

Fixture-isolated — assert the contract, not the live framework layout.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = str(Path(__file__).resolve().parent.parent / "tools")
sys.path.insert(0, TOOLS)

V4_LOCAL = os.path.join("WAI-Harness", "spoke", "local")
V4_ADVISORS = os.path.join("WAI-Harness", "spoke", "advisors")


def _mk_v4(tmp_path):
    """A v4-only spoke fixture (no WAI-Spoke tree → resolver returns v4)."""
    (tmp_path / "WAI-Harness" / "spoke" / "local").mkdir(parents=True)
    (tmp_path / "WAI-Harness" / "spoke" / "advisors").mkdir(parents=True)
    return str(tmp_path)


def _mk_v3(tmp_path):
    (tmp_path / "WAI-Spoke" / "advisors").mkdir(parents=True)
    return str(tmp_path)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)


# --- module-constant tools: _wai_base(root) resolves under WAI-Harness/spoke/local ---

@pytest.mark.parametrize("modname", [
    "burn_panel", "emit_activity_event", "mirror_track_to_events",
])
def test_module_tool_base_is_v4(modname, tmp_path):
    mod = __import__(modname)
    root = _mk_v4(tmp_path)
    base = mod._wai_base(root)
    assert base.endswith(V4_LOCAL), f"{modname}._wai_base -> {base}"
    assert "WAI-Spoke" not in base


# --- archie: advisors sibling + state under v4, scan tolerates real dict-wrapped index ---

def test_archie_resolves_v4(tmp_path):
    import archie_advisor as a
    root = _mk_v4(tmp_path)
    assert a._advisors(root).endswith(V4_ADVISORS)
    assert a._state_path(root).endswith(os.path.join(V4_LOCAL, "WAI-State.json"))


def test_archie_normalizes_dict_wrapped_index():
    import archie_advisor as a
    # v4 schedule-index is dict-wrapped; v3 was a bare list. Both must yield the inner list.
    assert a._advisor_entries({"advisors": [{"advisor_id": "x"}]}) == [{"advisor_id": "x"}]
    assert a._advisor_entries([{"advisor_id": "y"}]) == [{"advisor_id": "y"}]
    assert a._advisor_entries("garbage") == []


# --- validate_canonical: lugs root + contract spec resolve under v4 ---

def test_validate_canonical_lugs_root_is_v4(tmp_path):
    import validate_canonical as v
    root = _mk_v4(tmp_path)
    assert str(v._lugs_root(root)).endswith(os.path.join(V4_LOCAL, "lugs"))
    assert str(v._spec_path(root)).endswith(
        os.path.join(V4_LOCAL, "lugs", v.SPEC_SUFFIX.replace("/", os.sep)))


# --- ozi_autopilot + spoke_expediter: working base / advisors resolve under v4 ---

def test_ozi_safe_root_is_v4(tmp_path):
    import ozi_autopilot as o
    base = str(o._v4_safe_root(_mk_v4(tmp_path)))
    assert base.endswith(V4_LOCAL) and "WAI-Spoke" not in base


def test_expediter_resolves_v4(tmp_path):
    import spoke_expediter as e
    root = _mk_v4(tmp_path)
    assert e._base(root).endswith(V4_LOCAL)
    assert e._advisors_dir(root).endswith(V4_ADVISORS)


# --- spoke_cleanup: v4 short-circuit predicate ---

def test_spoke_cleanup_v4_shortcircuit(tmp_path, monkeypatch):
    import spoke_cleanup as c
    v4 = _mk_v4(tmp_path)
    monkeypatch.chdir(v4)
    assert c._is_v4_only(".") is True


def test_spoke_cleanup_runs_on_v3(tmp_path, monkeypatch):
    import spoke_cleanup as c
    v3 = _mk_v3(tmp_path)
    monkeypatch.chdir(v3)
    assert c._is_v4_only(".") is False


# --- write_cartographer_obs: end-to-end, writes under v4 local (subprocess) ---

def test_cartographer_writes_under_v4(tmp_path):
    root = Path(_mk_v4(tmp_path))
    (root / V4_LOCAL).mkdir(parents=True, exist_ok=True)
    (root / V4_LOCAL / "WAI-State.json").write_text(json.dumps(
        {"spoke_id": "fixture", "_session_state": {"session_id": "s-fix"}}))
    track = root / "track.jsonl"
    track.write_text(json.dumps({"event": "session_start", "model": "claude-x"}) + "\n")

    r = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "write_cartographer_obs.py"), str(track)],
        cwd=str(root), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    obs = list((root / V4_LOCAL / "cartographer" / "observations").glob("*.json"))
    assert obs, "no observation written under WAI-Harness/spoke/local/cartographer"
    # And nothing leaked into a phantom WAI-Spoke tree.
    assert not (root / "WAI-Spoke").exists()
