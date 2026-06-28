"""test_dead_end_scan.py — P3 of initiative-optimize-ceremonies-v1 / no-dead-ends gate."""
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import dead_end_scan  # noqa: E402


def _git(root, *a):
    return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, check=True)


def _repo(tmp):
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "t@t.t")
    _git(tmp, "config", "user.name", "t")
    _git(tmp, "checkout", "-q", "-b", "main")
    with open(os.path.join(tmp, "README.md"), "w") as fh:
        fh.write("x\n")
    _git(tmp, "add", "-A")
    _git(tmp, "commit", "-q", "-m", "init")
    return tmp


def test_clean_repo(tmp_path):
    tmp = _repo(str(tmp_path))
    rep = dead_end_scan.scan(tmp)
    assert rep["ok"] and rep["clean"], rep


def test_untracked_source_is_dead_end(tmp_path):
    tmp = _repo(str(tmp_path))
    with open(os.path.join(tmp, "orphan.py"), "w") as fh:
        fh.write("print('orphan')\n")
    rep = dead_end_scan.scan(tmp)
    assert not rep["clean"]
    assert "orphan.py" in rep["untracked_source"]


def test_uncommitted_is_dead_end(tmp_path):
    tmp = _repo(str(tmp_path))
    with open(os.path.join(tmp, "README.md"), "a") as fh:
        fh.write("more\n")
    rep = dead_end_scan.scan(tmp)
    assert not rep["clean"]
    assert "README.md" in rep["uncommitted"]


def test_stash_is_dead_end(tmp_path):
    tmp = _repo(str(tmp_path))
    with open(os.path.join(tmp, "README.md"), "a") as fh:
        fh.write("wip\n")
    _git(tmp, "stash")
    rep = dead_end_scan.scan(tmp)
    assert not rep["clean"]
    assert len(rep["stashes"]) == 1


def test_branch_ahead_reported_but_not_session_blocker(tmp_path):
    tmp = _repo(str(tmp_path))
    _git(tmp, "checkout", "-q", "-b", "session/x")
    with open(os.path.join(tmp, "f.py"), "w") as fh:
        fh.write("y\n")
    _git(tmp, "add", "-A")
    _git(tmp, "commit", "-q", "-m", "branch work")
    _git(tmp, "checkout", "-q", "main")
    rep = dead_end_scan.scan(tmp, scope="session")
    # branch ahead is reported...
    assert any(b["branch"] == "session/x" for b in rep["branches_ahead"])
    # ...but main itself is clean at session scope (no uncommitted/untracked/stash/unpushed)
    assert rep["clean"], rep
