"""test_ceremony_deploy_and_drift.py — P0 of initiative-optimize-ceremonies-v1.

Verifies deploy_commands.py syncs the canonical command set to the active dir
(preserving local-only commands, pruning retired ones) and that
ceremony_drift_check.py detects drift and passes when synced.
"""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import deploy_commands  # noqa: E402
import ceremony_drift_check  # noqa: E402


def _make_spoke(tmp):
    managed = os.path.join(tmp, "WAI-Harness", "spoke", "managed", ".claude", "commands")
    template = os.path.join(tmp, "WAI-Harness", "spoke", "managed", "templates", "commands")
    active = os.path.join(tmp, ".claude", "commands")
    for d in (managed, template, active):
        os.makedirs(d, exist_ok=True)
    return managed, template, active


def _write(path, name, body):
    with open(os.path.join(path, name), "w") as fh:
        fh.write(body)


def test_deploy_syncs_preserves_local_and_prunes_retired(tmp_path):
    tmp = str(tmp_path)
    managed, template, active = _make_spoke(tmp)
    # canonical
    _write(managed, "wai.md", "CANONICAL wai v2\n")
    _write(managed, "wai-savepoint.md", "CANONICAL savepoint v2\n")
    # active: stale wai, a local-only command, a retired command
    _write(active, "wai.md", "STALE wai v1\n")
    _write(active, "fable-review.md", "LOCAL only\n")
    _write(active, deploy_commands.RETIRED[0], "dead\n")

    rep = deploy_commands.deploy(tmp, dry_run=False)
    assert rep["ok"]
    # stale overwritten with canonical
    assert open(os.path.join(active, "wai.md")).read() == "CANONICAL wai v2\n"
    # new canonical deployed
    assert open(os.path.join(active, "wai-savepoint.md")).read() == "CANONICAL savepoint v2\n"
    # local-only preserved
    assert os.path.exists(os.path.join(active, "fable-review.md"))
    assert "fable-review.md" in rep["preserved_local"]
    # retired pruned
    assert not os.path.exists(os.path.join(active, deploy_commands.RETIRED[0]))
    assert deploy_commands.RETIRED[0] in rep["pruned"]


def test_deploy_idempotent(tmp_path):
    tmp = str(tmp_path)
    managed, template, active = _make_spoke(tmp)
    _write(managed, "wai.md", "X\n")
    deploy_commands.deploy(tmp, dry_run=False)
    rep2 = deploy_commands.deploy(tmp, dry_run=False)
    assert rep2["copied"] == [] and "wai.md" in rep2["already_current"]


def test_drift_check_detects_and_clears(tmp_path):
    tmp = str(tmp_path)
    managed, template, active = _make_spoke(tmp)
    _write(managed, "wai.md", "CANON\n")
    # template + active stale -> drift
    _write(template, "wai.md", "OLD\n")
    _write(active, "wai.md", "OLD\n")
    rep = ceremony_drift_check.check(tmp)
    assert not rep["ok"]
    assert rep["active_drift"] and rep["template_drift"]
    # sync both -> clean
    deploy_commands.deploy(tmp, dry_run=False)
    import shutil
    shutil.copy2(os.path.join(managed, "wai.md"), os.path.join(template, "wai.md"))
    rep2 = ceremony_drift_check.check(tmp)
    assert rep2["ok"], rep2


def test_drift_check_flags_retired_present(tmp_path):
    tmp = str(tmp_path)
    managed, template, active = _make_spoke(tmp)
    _write(managed, "wai.md", "C\n")
    _write(active, "wai.md", "C\n")
    _write(template, "wai.md", "C\n")
    _write(managed, deploy_commands.RETIRED[0], "zombie\n")
    rep = ceremony_drift_check.check(tmp)
    assert not rep["ok"]
    assert any(r["file"] == deploy_commands.RETIRED[0] for r in rep["retired_present"])
