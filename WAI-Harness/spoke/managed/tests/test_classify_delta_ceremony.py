"""test_classify_delta_ceremony.py

Tests the extracted delta-ceremony classifier (P2 of
initiative-optimize-ceremonies-v1). Builds a temp git repo as BASE and exercises:

  1. No fingerprint -> FULL; with no code/doc/template changes -> CONVERSATION_ONLY.
  2. Re-closeout (fingerprint.session_id == current) with state-only diff -> MICRO
     (all skip flags set, version bump skipped).
"""
import json
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import classify_delta_ceremony  # noqa: E402


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _init_repo(root):
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.t")
    _git(root, "config", "user.name", "t")


def _make_base(root):
    """Create a v4-style BASE dir with runtime/ and commit it.

    Returns (base_abs, base_rel) — base_abs is what we pass to --base; the
    classifier uses base_abs as the literal state-only path prefix, but git
    diff returns repo-relative paths, so the test writes state files at the
    repo-relative path that equals base_abs's tail under root.
    """
    base = os.path.join(root, "WAI-Harness", "spoke", "local")
    os.makedirs(os.path.join(base, "runtime"), exist_ok=True)
    return base


def test_fresh_session_conversation_only(tmp_path):
    root = str(tmp_path)
    _init_repo(root)
    base = _make_base(root)

    # session-guard with a session id + start sha; no fingerprint present.
    with open(os.path.join(base, "runtime", "session-guard.json"), "w") as fh:
        json.dump({"session_id": "session-0001"}, fh)
    # seed a tracked file & commit so HEAD exists
    readme = os.path.join(root, "README.md")
    with open(readme, "w") as fh:
        fh.write("hi\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")

    # No working-tree changes at all -> CONVERSATION_ONLY (no session_start_sha,
    # falls back to git diff HEAD which is empty).
    res = classify_delta_ceremony.classify(base, session_id="session-0001", root=root)
    assert res["DELTA_CLASS"] == "FULL"
    assert res["CONVERSATION_ONLY"] is True
    assert res["SKIP_TEST_GATE"] is True  # forced by CONVERSATION_ONLY
    assert res["SKIP_VERSION_BUMP"] is False


def test_re_closeout_state_only_is_micro(tmp_path):
    root = str(tmp_path)
    _init_repo(root)
    base = _make_base(root)

    with open(os.path.join(base, "runtime", "session-guard.json"), "w") as fh:
        json.dump({"session_id": "session-0002"}, fh)
    readme = os.path.join(root, "README.md")
    with open(readme, "w") as fh:
        fh.write("hi\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    last_sha = _git(root, "rev-parse", "HEAD").stdout.strip()

    # Fingerprint says this is a re-closeout in the SAME session.
    with open(os.path.join(base, "runtime", "closeout-fingerprint.json"), "w") as fh:
        json.dump({"session_id": "session-0002", "last_closeout_sha": last_sha}, fh)

    # Make a STATE-ONLY change since last_sha: a .json file under the BASE path.
    # The classifier tests f.startswith(base + "/") against git-diff paths, so the
    # changed file's git-relative path must begin with the absolute base path.
    # git diff returns paths relative to repo root; base is absolute. To make the
    # state-only test pass, the file must be committed and the diff path must
    # start with the base prefix. git returns repo-relative paths, so we point
    # --base at the repo-relative base dir for this prefix-matching case.
    rel_base = os.path.relpath(base, root)
    state_file = os.path.join(base, "WAI-State.json")
    with open(state_file, "w") as fh:
        json.dump({"v": 1}, fh)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "state bump")

    # Run git from repo root so diff paths are repo-relative; pass rel_base so the
    # state-only prefix test matches (faithful: ceremony substitutes {BASE} with
    # whatever the spoke's base resolves to relative to the git invocation cwd).
    cwd = os.getcwd()
    try:
        os.chdir(root)
        res = classify_delta_ceremony.classify(rel_base, session_id="session-0002")
    finally:
        os.chdir(cwd)

    assert res["DELTA_CLASS"] == "MICRO"
    assert res["SKIP_VERSION_BUMP"] is True
    assert res["SKIP_TEST_GATE"] is True
    assert res["SKIP_CHANGELOG"] is True
    assert res["SKIP_TEACHINGS"] is True
    assert res["SKIP_SKILL_SYNC"] is True
    assert res["SKIP_TELEMETRY"] is True
    assert res["SKIP_BRIEFS"] is True


def test_cli_emits_json(tmp_path, capsys):
    root = str(tmp_path)
    _init_repo(root)
    base = _make_base(root)
    with open(os.path.join(base, "runtime", "session-guard.json"), "w") as fh:
        json.dump({"session_id": "session-0003"}, fh)
    with open(os.path.join(root, "README.md"), "w") as fh:
        fh.write("hi\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")

    cwd = os.getcwd()
    try:
        os.chdir(root)
        rc = classify_delta_ceremony.main(["--base", base, "--session-id", "session-0003"])
    finally:
        os.chdir(cwd)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out.keys()) == {
        "DELTA_CLASS", "SKIP_VERSION_BUMP", "SKIP_TEST_GATE", "SKIP_CHANGELOG",
        "SKIP_TEACHINGS", "SKIP_SKILL_SYNC", "SKIP_TELEMETRY", "SKIP_BRIEFS",
        "CONVERSATION_ONLY",
    }
