#!/usr/bin/env python3
"""Tests for spoke_cleanup.py v4 short-circuit.

spoke_cleanup restructures the legacy v3 WAI-Spoke/ tree. On a v4-only spoke
there is no WAI-Spoke/ tree, so the tool must short-circuit with a clear NOTICE
and exit 0 WITHOUT creating or restructuring anything — rather than silently
no-op'ing. A genuine v3 spoke (WAI-Spoke/ present) must NOT short-circuit.
"""
import os
import sys
import contextlib
import io

TOOLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"
)
sys.path.insert(0, TOOLS_DIR)

import spoke_cleanup  # noqa: E402


def _v4_only_spoke(tmp_path):
    """Build a v4-only spoke_root: WAI-Harness/spoke/local present, NO WAI-Spoke."""
    root = tmp_path / "spoke"
    (root / "WAI-Harness" / "spoke" / "local").mkdir(parents=True)
    return root


def _v3_spoke(tmp_path):
    """Build a v3 spoke_root: WAI-Spoke present (legacy layout)."""
    root = tmp_path / "spoke"
    (root / "WAI-Spoke" / "lugs").mkdir(parents=True)
    return root


def _run_main_in(root, monkeypatch, *, mode=None):
    """Run spoke_cleanup.main() with cwd=root and captured argv/stdout."""
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", ["spoke_cleanup.py"])
    if mode is not None:
        monkeypatch.setenv("WAI_HARNESS_MODE", mode)
    else:
        monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = spoke_cleanup.main()
    return rc, buf.getvalue()


def test_is_v4_only_true_for_v4_spoke(tmp_path, monkeypatch):
    root = _v4_only_spoke(tmp_path)
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
    assert spoke_cleanup.is_v4_only(str(root)) is True


def test_is_v4_only_false_for_v3_spoke(tmp_path, monkeypatch):
    root = _v3_spoke(tmp_path)
    monkeypatch.delenv("WAI_HARNESS_MODE", raising=False)
    assert spoke_cleanup.is_v4_only(str(root)) is False


def test_v4_only_shortcircuits_clean(tmp_path, monkeypatch):
    root = _v4_only_spoke(tmp_path)

    before = set(p.name for p in root.iterdir())
    rc, out = _run_main_in(root, monkeypatch, mode="v4-only")

    # Exits cleanly (0) with the v4 NOTICE.
    assert rc == 0
    assert "v4-only" in out
    assert "Nothing to clean" in out
    assert "SPOKE CLEANUP" not in out  # never entered the restructure path

    # Created / restructured nothing: no WAI-Spoke tree appeared.
    after = set(p.name for p in root.iterdir())
    assert after == before
    assert not (root / "WAI-Spoke").exists()


def test_v3_does_not_shortcircuit(tmp_path, monkeypatch):
    root = _v3_spoke(tmp_path)

    rc, out = _run_main_in(root, monkeypatch, mode="v3-only")

    # The v4 NOTICE must be absent and it must reach the v3 restructure path.
    assert "Nothing to clean" not in out
    assert "SPOKE CLEANUP" in out
    # main() falls through to completion for a v3 spoke (returns None / 0).
    assert (rc or 0) == 0
