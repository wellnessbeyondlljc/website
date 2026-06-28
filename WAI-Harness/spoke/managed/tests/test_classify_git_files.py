#!/usr/bin/env python3
"""Verification test for classify_git_files.py (P2 ceremony extraction).

Builds a temp git repo with uncommitted files in each bucket and asserts the
tool classifies them exactly as the inline closeout block did (teaching /
runtime / unknown), including {BASE} expansion and rename ('A -> B') handling.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(
        mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CGF = _load("classify_git_files")

BASE = "WAI-Spoke"


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True,
                   capture_output=True, text=True)


def _write(repo, relpath, content="x"):
    full = os.path.join(repo, relpath)
    os.makedirs(os.path.dirname(full) or repo, exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


def _init_repo(tmp):
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "t@t.t")
    _git(tmp, "config", "user.name", "t")
    return tmp


def test_buckets_classification():
    with tempfile.TemporaryDirectory() as tmp:
        _init_repo(tmp)

        # teaching bucket
        _write(tmp, f"{BASE}/seed/ingest/processed/t1.md")
        _write(tmp, ".claude/hooks/foo.sh")
        _write(tmp, "CLAUDE.md")
        _write(tmp, "AGENTS.md")

        # runtime bucket
        _write(tmp, f"{BASE}/runtime/session-guard.json")
        _write(tmp, f"{BASE}/advisors/a.json")
        _write(tmp, "wakeup-brief.json")
        _write(tmp, f"{BASE}/wakeup-brief.json")
        _write(tmp, f"{BASE}/sessions/session-1/track.jsonl")

        # unknown bucket
        _write(tmp, "src/main.py")
        _write(tmp, "README.txt")

        # Stage everything so git status emits full per-file paths (untracked
        # directories are otherwise collapsed to 'dir/' by --short).
        _git(tmp, "add", "-A")

        out = CGF.classify(BASE, root=tmp)

        assert set(out["teaching"]) == {
            f"{BASE}/seed/ingest/processed/t1.md",
            ".claude/hooks/foo.sh",
            "CLAUDE.md",
            "AGENTS.md",
        }, out["teaching"]
        assert set(out["runtime"]) == {
            f"{BASE}/runtime/session-guard.json",
            f"{BASE}/advisors/a.json",
            "wakeup-brief.json",
            f"{BASE}/wakeup-brief.json",
            f"{BASE}/sessions/session-1/track.jsonl",
        }, out["runtime"]
        assert set(out["unknown"]) == {"src/main.py", "README.txt"}, out["unknown"]


def test_rename_uses_destination_path():
    with tempfile.TemporaryDirectory() as tmp:
        _init_repo(tmp)
        # Commit a tracked file, then git-mv it into a teaching path so status
        # emits a rename line 'old -> new'.
        _write(tmp, "old.md")
        _git(tmp, "add", "old.md")
        _git(tmp, "commit", "-qm", "init")
        _git(tmp, "mv", "old.md", "CLAUDE.md")

        out = CGF.classify(BASE, root=tmp)
        # Destination path (CLAUDE.md) decides the bucket -> teaching.
        assert "CLAUDE.md" in out["teaching"], out
        assert out["runtime"] == []
        assert out["unknown"] == []


def test_cli_emits_json():
    with tempfile.TemporaryDirectory() as tmp:
        _init_repo(tmp)
        _write(tmp, "CLAUDE.md")
        _write(tmp, "src/x.py")
        _git(tmp, "add", "-A")
        proc = subprocess.run(
            [sys.executable,
             os.path.join(ROOT, "tools", "classify_git_files.py"),
             "--base", BASE, "--root", tmp],
            capture_output=True, text=True, check=True)
        data = json.loads(proc.stdout)
        assert data["teaching"] == ["CLAUDE.md"], data
        assert data["unknown"] == ["src/x.py"], data
        assert data["runtime"] == [], data


def test_empty_repo():
    with tempfile.TemporaryDirectory() as tmp:
        _init_repo(tmp)
        out = CGF.classify(BASE, root=tmp)
        assert out == {"teaching": [], "runtime": [], "unknown": []}, out


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
