"""Regression test for impl-fix-p2-v3noop-sweep-v1.

The RFC verification branch in OziAutopilot._execute_lugs used to point rfc_out at
self.spoke_root/"WAI-Spoke"/"lugs"/"outgoing", a phantom tree on a v4-only spoke. The
verify therefore always reported "rfc_response not found" and the RFC loop died. The
fix resolves the outgoing dir via the v4-aware base (self.spoke_wai), and the two
agent-prompt strings in _inject_rfc_instructions point the spawned agent at the SAME
resolved dir.

These tests construct a minimal v4 fixture spoke and assert both the verify path and
the prompt path resolve under WAI-Harness/spoke/local/lugs/outgoing, NOT WAI-Spoke.
"""
import os
import sys
import types
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import ozi_autopilot  # noqa: E402


@pytest.fixture
def v4_spoke(tmp_path, monkeypatch):
    """A minimal v4-only spoke root: WAI-Harness/spoke/local exists, no WAI-Spoke."""
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    root = tmp_path / "myspoke"
    local = root / "WAI-Harness" / "spoke" / "local"
    (local / "lugs" / "outgoing").mkdir(parents=True, exist_ok=True)
    (root / "WAI-Harness" / "spoke" / "advisors").mkdir(parents=True, exist_ok=True)
    return root


def _make_ozi(spoke_root):
    """Construct an OziAutopilot bound to spoke_root, stubbing the heavy Ozi machinery."""
    monkey = pytest.MonkeyPatch()
    # OziConfig/Scanner/Dispatch only need to instantiate; replace with no-op stubs.
    monkey.setattr(ozi_autopilot, "OziConfig", lambda **kw: types.SimpleNamespace(**kw))
    monkey.setattr(ozi_autopilot, "OziScanner", lambda cfg: object())
    monkey.setattr(ozi_autopilot, "OziDispatch", lambda cfg: object())
    try:
        ozi = ozi_autopilot.OziAutopilot(
            spoke_path=Path(spoke_root),
            budget=1,
            hub_dir=None,
            dry_run=True,
            token_limit=1000,
            token_stop_threshold=1000,
        )
    finally:
        monkey.undo()
    return ozi


def test_spoke_wai_resolves_to_v4_local(v4_spoke):
    ozi = _make_ozi(v4_spoke)
    # The v4-aware base must be WAI-Harness/spoke/local, never the phantom WAI-Spoke tree.
    assert ozi.spoke_wai == v4_spoke / "WAI-Harness" / "spoke" / "local"
    assert "WAI-Spoke" not in str(ozi.spoke_wai)


def test_rfc_out_path_under_v4_local(v4_spoke):
    """The verify-branch rfc_out path resolves under WAI-Harness/spoke/local/lugs/outgoing."""
    ozi = _make_ozi(v4_spoke)
    lug_id = "rfc-lug-123"
    rfc_out = ozi.spoke_wai / "lugs" / "outgoing" / f"rfc-response-{lug_id}.json"
    expected = (
        v4_spoke / "WAI-Harness" / "spoke" / "local"
        / "lugs" / "outgoing" / f"rfc-response-{lug_id}.json"
    )
    assert rfc_out == expected
    assert "WAI-Spoke" not in str(rfc_out)


def test_prompt_points_at_same_v4_outgoing(v4_spoke):
    """The agent-prompt strings reference the SAME resolved outgoing dir as verify."""
    ozi = _make_ozi(v4_spoke)
    lug = {
        "id": "rfc-lug-123",
        "execute": "do the thing",
    }
    learn_directive = {
        "rfc_job_id": "job-1",
        "cohort_index": 0,
        "feedback_questions": ["was it clear?"],
        "dry_run": True,
    }
    injected = ozi._inject_rfc_instructions(lug, learn_directive)
    execute_text = injected["execute"]

    # The relative outgoing dir the prompt should use.
    out_dir = ozi.spoke_wai / "lugs" / "outgoing"
    rel = str(out_dir.relative_to(ozi.spoke_root))

    # The prompt must instruct writing to the resolved outgoing dir (v4 local path),
    # not the hardcoded phantom WAI-Spoke path.
    assert f"{rel}/rfc-response-rfc-lug-123.json" in execute_text
    assert f"mkdir -p {rel}" in execute_text
    assert "WAI-Spoke/lugs/outgoing/rfc-response" not in execute_text
    assert "mkdir -p WAI-Spoke/lugs/outgoing" not in execute_text
    # Sanity: the relative dir lands under spoke/local (v4), not WAI-Spoke.
    assert "WAI-Harness" in rel and "WAI-Spoke" not in rel
