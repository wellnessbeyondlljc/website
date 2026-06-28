#!/usr/bin/env python3
"""Verify mirror_track_to_events resolves paths under the active harness base.

v4-only -> sessions/track/state under WAI-Harness/spoke/local (NO WAI-Spoke segment).
v3      -> under WAI-Spoke.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import mirror_track_to_events as mtte  # noqa: E402


def _mk_v4(root):
    os.makedirs(os.path.join(root, "WAI-Harness", "spoke", "local", "sessions"))
    # .activated marker not needed: with no WAI-Spoke tree, only-v4 resolves v4.


def _mk_v3(root):
    os.makedirs(os.path.join(root, "WAI-Spoke", "sessions"))


def test_v4_paths_no_wai_spoke_segment(tmp_path, monkeypatch):
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    root = str(tmp_path)
    _mk_v4(root)
    p = mtte._resolve_paths(root, "session-20260623-0001")

    base = os.path.join(root, "WAI-Harness", "spoke", "local")
    assert p["sessions_dir"] == os.path.join(base, "sessions")
    assert p["track_path"] == os.path.join(base, "sessions", "session-20260623-0001", "track.jsonl")
    assert p["state_path"] == os.path.join(base, "WAI-State.json")
    for v in (p["sessions_dir"], p["track_path"], p["state_path"]):
        assert "WAI-Spoke" not in v


def test_v3_paths_under_wai_spoke(tmp_path, monkeypatch):
    monkeypatch.setenv("WAI_HARNESS_MODE", "v3-only")
    root = str(tmp_path)
    _mk_v3(root)
    p = mtte._resolve_paths(root, "session-20260623-0002")

    base = os.path.join(root, "WAI-Spoke")
    assert p["sessions_dir"] == os.path.join(base, "sessions")
    assert p["track_path"] == os.path.join(base, "sessions", "session-20260623-0002", "track.jsonl")
    assert p["state_path"] == os.path.join(base, "WAI-State.json")


def test_no_session_id_track_path_none(tmp_path, monkeypatch):
    monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
    root = str(tmp_path)
    _mk_v4(root)
    p = mtte._resolve_paths(root, None)
    assert p["track_path"] is None
    assert "WAI-Spoke" not in p["sessions_dir"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
