"""Test-at-birth for harness_status.py + the .claude coexistence resolver.

Proves v4 runs while TOLERATING v3 legacy files, and that basic interrogation
works in every mode (the patch-safety overlap):
  - detect() reports v3-only / v4-only / coexist / none correctly
  - active selection prefers v4 but honors a v3 override (the fallback path)
  - coexist surfaces both + the v4 managed integrity (missed/corrupt file visible)
  - the .claude/hooks/harness_mode.sh resolver yields the same answers in bash
  - install carries the Basher .claude set (hooks + settings) into a spoke
"""
import json
import os
import subprocess
from pathlib import Path

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness_status as hs
import harness_upgrade as hu


def _spoke(tmp, v3=False, v4=False):
    root = tmp / "spoke"
    root.mkdir(parents=True, exist_ok=True)
    if v3:
        (root / "WAI-Spoke").mkdir(parents=True, exist_ok=True)
    if v4:
        (root / "WAI-Harness" / "spoke" / "managed").mkdir(parents=True, exist_ok=True)
    return root


def test_detect_modes(tmp_path):
    assert hs.detect(_spoke(tmp_path / "a", v3=True))["mode"] == "v3-only"
    assert hs.detect(_spoke(tmp_path / "b", v4=True))["mode"] == "v4-only"
    assert hs.detect(_spoke(tmp_path / "c", v3=True, v4=True))["mode"] == "coexist"
    assert hs.detect(_spoke(tmp_path / "d"))["mode"] == "none"


def test_active_prefers_v4_but_honors_override(tmp_path):
    root = _spoke(tmp_path, v3=True, v4=True)
    assert hs.detect(root)["active"] == "v4"                  # default prefers v4
    assert hs.detect(root, override="v3")["active"] == "v3"   # fallback to legacy
    # an override to a mode that isn't present is ignored (stays usable)
    v3only = _spoke(tmp_path / "x", v3=True)
    assert hs.detect(v3only, override="v4")["active"] == "v3"


def test_v3_only_never_errors_and_reports_no_v4_managed(tmp_path):
    info = hs.detect(_spoke(tmp_path, v3=True))
    assert info["v4_present"] is False
    assert info["v4_managed_verify"] is None      # nothing to interrogate, no crash


def test_coexist_surfaces_v4_managed_integrity(tmp_path):
    # build a real v4 install so the managed verify runs
    master = tmp_path / "master"
    mm = master / "spoke" / "managed"
    (mm / "tools").mkdir(parents=True)
    (mm / "tools" / "a.py").write_text("v1\n")
    man = hu.build_manifest(mm, generated_at="2026-01-01T00:00:00Z")
    (mm / hu.MANIFEST_NAME).write_text(json.dumps(man, indent=2))

    spoke = tmp_path / "spoke"
    (spoke / "WAI-Spoke").mkdir(parents=True)         # legacy present
    hu.install(master, spoke)                          # adds WAI-Harness
    info = hs.detect(spoke)
    assert info["mode"] == "coexist"
    assert info["v4_managed_verify"]["ok"] is True
    # corrupt a managed file -> interrogation surfaces drift (patchable via v3 overlap)
    (spoke / "WAI-Harness" / "spoke" / "managed" / "tools" / "a.py").write_text("tampered\n")
    assert hs.detect(spoke)["v4_managed_verify"]["ok"] is False


def test_claude_resolver_bash_matches(tmp_path):
    resolver = HERE.parent / ".claude" / "hooks" / "harness_mode.sh"
    assert resolver.exists(), "harness_mode.sh must ship in managed/.claude/hooks"
    root = _spoke(tmp_path, v3=True, v4=True)
    out = subprocess.run(
        ["bash", "-c", f'source "{resolver}" "{root}"; echo "$HARNESS_MODE $HARNESS_ACTIVE"'],
        capture_output=True, text=True)
    assert out.stdout.strip() == "coexist v4"
    # override to v3 via env
    out2 = subprocess.run(
        ["bash", "-c", f'WAI_HARNESS_MODE=v3 bash -c \'source "{resolver}" "{root}"; echo "$HARNESS_ACTIVE"\''],
        capture_output=True, text=True)
    assert out2.stdout.strip() == "v3"


def test_install_carries_basher_claude_set(tmp_path):
    # the master must distribute the Basher-managed .claude set or v4 cannot run
    master_managed = HERE.parent  # .../spoke/managed
    claude = master_managed / ".claude"
    assert (claude / "hooks" / "harness_mode.sh").exists()
    assert (claude / "hooks" / "session-start.sh").exists()
    assert (claude / "settings.json").exists()
    # and these .claude files are tracked in the master MANIFEST (distributed, verified)
    man = hu.load_manifest(master_managed)
    assert any(f.startswith(".claude/hooks/") for f in man["files"])
    assert ".claude/settings.json" in man["files"]
