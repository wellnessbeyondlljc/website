#!/usr/bin/env python3
"""Path-resolution tests for emit_activity_event._resolve_paths.

Asserts the helper resolves the activity queue + WAI-State.json under the
harness-mode-aware working base:
  v4 (WAI_HARNESS_MODE=v4-only) -> <root>/WAI-Harness/spoke/local/...
                                   (NO 'WAI-Spoke' segment)
  v3                            -> <root>/WAI-Spoke/...
"""
import importlib
import os
import sys

import pytest

_TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, _TOOLS)

import emit_activity_event as eae  # noqa: E402


def _mkspoke_v4(root):
    os.makedirs(os.path.join(root, "WAI-Harness", "spoke", "local", "runtime"))
    # marker forcing v4 even if a WAI-Spoke tree also existed (coexist safety)
    open(os.path.join(root, "WAI-Harness", "spoke", ".activated"), "w").close()


def _mkspoke_v3(root):
    os.makedirs(os.path.join(root, "WAI-Spoke", "runtime"))


def test_v4_paths_under_local(tmp_path, monkeypatch):
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    root = str(tmp_path)
    _mkspoke_v4(root)

    queue_path, state_path = eae._resolve_paths(root)

    v4_base = os.path.join(root, "WAI-Harness", "spoke", "local")
    assert queue_path == os.path.join(v4_base, "runtime", "activity-events-queue.jsonl")
    assert state_path == os.path.join(v4_base, "WAI-State.json")
    # no legacy segment anywhere on the v4 paths
    assert "WAI-Spoke" not in queue_path
    assert "WAI-Spoke" not in state_path


def test_v3_paths_under_wai_spoke(tmp_path, monkeypatch):
    monkeypatch.setenv("WAI_HARNESS_MODE", "v3-only")
    root = str(tmp_path)
    _mkspoke_v3(root)

    queue_path, state_path = eae._resolve_paths(root)

    assert queue_path == os.path.join(root, "WAI-Spoke", "runtime", "activity-events-queue.jsonl")
    assert state_path == os.path.join(root, "WAI-Spoke", "WAI-State.json")


def test_no_tree_falls_back_to_v3_strings(tmp_path, monkeypatch):
    """Guarded fallback: when neither tree resolves, the raw WAI-Spoke/ strings
    are used (never None / never a crash)."""
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
    root = str(tmp_path)  # empty: no WAI-Harness, no WAI-Spoke

    queue_path, state_path = eae._resolve_paths(root)

    assert queue_path == os.path.join(root, "WAI-Spoke", "runtime", "activity-events-queue.jsonl")
    assert state_path == os.path.join(root, "WAI-Spoke", "WAI-State.json")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
