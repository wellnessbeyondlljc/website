#!/usr/bin/env python3
"""Lugs carry a worktree `origin` so cross-worktree reconciliation can locate work.

Regression lock for the S135 drift (8 worktrees / 7 branches stranded off main):
a lug must record which worktree+branch it lives in, stamped at creation and
refreshed on every mutating write, and lug_worktree_map must consume it without
choking on legacy string-valued origin fields.
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import lug_utils  # noqa: E402
import new_lug  # noqa: E402
import lug_worktree_map  # noqa: E402


def test_resolve_worktree_origin_shape():
    o = lug_utils.resolve_worktree_origin(".")
    assert set(o) == {"worktree", "worktree_name", "branch", "git_sha", "stamped_at"}
    # inside this repo, git fields resolve (never raises even outside one)
    assert o["worktree"] and o["git_sha"]


def test_creation_stamps_origin():
    lug = new_lug.build_v4_lug("test-origin-create", "impl", "t",
                               spoke_path=".", situation="origin stamping at creation")
    assert "origin" in lug and isinstance(lug["origin"], dict)
    assert lug["origin"]["git_sha"]
    assert "origin" in new_lug.AUTO_FIELDS


def test_bump_rev_refreshes_origin():
    lug = {"id": "x", "type": "impl", "rev": 1}
    res = lug_utils.prepare_lug_write(lug, 1)
    assert res["ok"] and lug["rev"] == 2
    assert isinstance(lug.get("origin"), dict) and lug["origin"]["git_sha"]


def test_map_tolerates_legacy_string_origin(tmp_path):
    # a lug store with a legacy origin:str must not crash the scanner
    store = tmp_path / "WAI-Harness/spoke/local/lugs/bytype/impl/open"
    store.mkdir(parents=True)
    (store / "legacy.json").write_text(
        '{"id":"legacy","type":"impl","status":"open","origin":"some old string"}')
    recs = list(lug_worktree_map.scan_worktree(str(tmp_path)))
    assert len(recs) == 1
    assert recs[0][0] == "legacy"
    assert recs[0][1]["origin_worktree"] is None


if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
