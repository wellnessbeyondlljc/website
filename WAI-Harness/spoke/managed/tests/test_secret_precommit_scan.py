"""Acceptance proof: pre-commit secret scanner + hook installer (Fable MR-2).

Asserts the built-in high-confidence scanner catches the secret CLASSES the 2026-06-12 Fable
review actually found, does not flag placeholders/templates, and that the installer wires
core.hooksPath idempotently on a throwaway git repo.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = str(Path(__file__).resolve().parent.parent / "tools")
sys.path.insert(0, TOOLS)

import secret_precommit_scan as S  # noqa: E402
import install_git_hooks as I      # noqa: E402


# --- detection: each high-confidence class the review found ---

@pytest.mark.parametrize("text,rule_substr", [
    ("ANTHROPIC_API_KEY=sk-ant-api03-" + "a" * 80, "Anthropic"),
    ("aws_access_key_id = AKIA" + "A" * 16, "AWS"),
    ("google: AIza" + "b" * 35, "Google"),
    ("gh = ghp_" + "c" * 36, "GitHub"),
    ("-----BEGIN OPENSSH PRIVATE KEY-----", "Private key"),  # gitleaks:allow (test fixture)
    ('stripe = "sk_live_' + "d" * 30 + '"', "Stripe"),
    ('config = {"password": "' + "Zx9" * 12 + '"}', "Generic assigned secret"),
])
def test_detects_secret_classes(text, rule_substr):
    found = S.scan_text(text)
    assert found, f"missed: {rule_substr}"
    assert any(rule_substr in f["rule"] for f in found), [f["rule"] for f in found]


def test_finding_is_redacted():
    # the printed match must not echo the full secret
    secret = "sk-ant-api03-" + "a" * 80
    f = S.scan_text(f"key={secret}")[0]
    assert secret not in f["match"] and "…" in f["match"]


# --- no false positives on placeholders / templates / clean code ---

@pytest.mark.parametrize("text", [
    "ANTHROPIC_API_KEY=sk-ant-api03-<your-key-here>",
    "API_KEY=your-api-key-goes-here",
    "password = 'changeme-example-placeholder'",
    "token=xxxxxxxxxxxxxxxxxxxxxxxx",
    "def compute_total(rows):  # ordinary code, no secrets\n    return sum(r.v for r in rows)",
    "AKIAEXAMPLE = not-a-real-16-char-id",
])
def test_no_false_positive(text):
    assert S.scan_text(text) == [], S.scan_text(text)


def test_inline_allow_marker_suppresses():
    real = "AKIA" + "A" * 16
    assert S.scan_text(f"key = {real}")  # detected without marker
    assert S.scan_text(f"key = {real}  # gitleaks:allow") == []
    assert S.scan_text(f"key = {real}  # pragma: allowlist secret") == []


# --- installer wires core.hooksPath idempotently on a real temp repo ---

def _init_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "t"], check=True)
    return tmp_path


def test_installer_sets_hooks_path_idempotently(tmp_path):
    root = _init_repo(tmp_path)
    r1 = I.install(str(root))
    assert r1["ok"], r1
    cur = subprocess.run(["git", "-C", str(root), "config", "--get", "core.hooksPath"],
                         capture_output=True, text=True).stdout.strip()
    assert cur == ".githooks"
    assert (root / ".githooks" / "pre-commit").exists()
    assert os.access(root / ".githooks" / "pre-commit", os.X_OK)
    assert (root / ".gitleaks.toml").exists()
    # re-run is a no-op success
    r2 = I.install(str(root))
    assert r2["ok"] and any("already .githooks" in a for a in r2["actions"])


def test_installed_hook_blocks_a_real_secret_commit(tmp_path):
    root = _init_repo(tmp_path)
    # point the hook's scanner lookup at the live managed tools via a symlink layout
    tools_dir = root / "WAI-Harness" / "spoke" / "managed" / "tools"
    tools_dir.mkdir(parents=True)
    for t in ("secret_precommit_scan.py",):
        (tools_dir / t).write_text(Path(TOOLS, t).read_text())
    assert I.install(str(root))["ok"]

    (root / "leak.txt").write_text("ANTHROPIC_API_KEY=sk-ant-api03-" + "a" * 80 + "\n")
    subprocess.run(["git", "-C", str(root), "add", "leak.txt"], check=True)
    r = subprocess.run(["git", "-C", str(root), "commit", "-m", "oops"],
                       capture_output=True, text=True)
    assert r.returncode != 0, "hook should have blocked the secret commit"
    assert "BLOCKED" in (r.stdout + r.stderr) or "blocked" in (r.stdout + r.stderr)
