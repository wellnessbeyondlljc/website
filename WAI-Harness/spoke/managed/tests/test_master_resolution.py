"""Acceptance proof: harness_upgrade.resolve_master — portable master path resolution.
$WAI_HARNESS_MASTER env -> per-spoke WAI-Harness/.harness-master -> built-in fallback.
This is what lets a spoke cloned to another machine self-update from a reachable master.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import harness_upgrade as hu  # noqa: E402


def test_fallback_when_nothing_set(tmp_path, monkeypatch):
    monkeypatch.delenv("WAI_HARNESS_MASTER", raising=False)
    spoke = tmp_path / "s"; (spoke / "WAI-Harness").mkdir(parents=True)
    assert hu.resolve_master(str(spoke), fallback="/fallback/master") == "/fallback/master"


def test_per_spoke_config_file_overrides_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("WAI_HARNESS_MASTER", raising=False)
    spoke = tmp_path / "s"; (spoke / "WAI-Harness").mkdir(parents=True)
    (spoke / "WAI-Harness" / hu.MASTER_CONFIG).write_text("/other/machine/WAI-Harness\n")
    assert hu.resolve_master(str(spoke), fallback="/fallback") == "/other/machine/WAI-Harness"


def test_env_overrides_everything(tmp_path, monkeypatch):
    spoke = tmp_path / "s"; (spoke / "WAI-Harness").mkdir(parents=True)
    (spoke / "WAI-Harness" / hu.MASTER_CONFIG).write_text("/config/path")
    monkeypatch.setenv("WAI_HARNESS_MASTER", "/env/wins/WAI-Harness")
    assert hu.resolve_master(str(spoke), fallback="/fallback") == "/env/wins/WAI-Harness"


def test_no_spoke_root_uses_fallback(monkeypatch):
    monkeypatch.delenv("WAI_HARNESS_MASTER", raising=False)
    assert hu.resolve_master(None, fallback="/fb") == "/fb"


def test_pull_uses_resolved_master_offline_noop(tmp_path, monkeypatch):
    # a spoke whose resolved master does not exist -> pull no-ops (offline preserved), never errors
    monkeypatch.setenv("WAI_HARNESS_MASTER", str(tmp_path / "nonexistent" / "WAI-Harness"))
    spoke = tmp_path / "s"; (spoke / "WAI-Harness" / "spoke" / "managed").mkdir(parents=True)
    res = hu.pull(str(spoke))   # master_root=None -> resolves to the bad env path
    assert res["status"] == "no-master" and res["pulled"] == 0
