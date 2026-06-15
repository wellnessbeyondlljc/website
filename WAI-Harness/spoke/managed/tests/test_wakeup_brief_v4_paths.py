"""Acceptance proof: generate_wakeup_brief.py is harness-mode-aware (V4-COMPLETE Phase B).

The brief generator must resolve its working BASE via wai_paths and map that base back
to the spoke project root layout-aware — so a v4-only wakeup briefs from the v4 tree and
the coverage/drift/qa helpers stay correct when the base is .../WAI-Harness/spoke/local
(whose .parent is NOT the project root).
"""
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_gwb():
    spec = importlib.util.spec_from_file_location(
        "gwb_v4_paths", os.path.join(str(ROOT), "tools", "generate_wakeup_brief.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_project_root_for_v3_base(tmp_path):
    gwb = _load_gwb()
    base = tmp_path / "WAI-Spoke"
    assert gwb._project_root_for(base) == tmp_path


def test_project_root_for_v4_base(tmp_path):
    gwb = _load_gwb()
    base = tmp_path / "WAI-Harness" / "spoke" / "local"
    # the whole point: v4 base maps back to <root>, NOT to .parent (.../spoke)
    assert gwb._project_root_for(base) == tmp_path
    assert gwb._project_root_for(base) != base.parent


def test_project_root_for_unknown_layout_is_identity(tmp_path):
    gwb = _load_gwb()
    weird = tmp_path / "something-else"
    assert gwb._project_root_for(weird) == weird
