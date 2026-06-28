#!/usr/bin/env python3
"""Tests for savepoint_migrate.py — legacy savepoints -> Initiative>Savepoint.

Covers:
  * dry-run/live PARITY: --dry-run reports the same `relocated` total a live run
    writes, including the WAI-State._savepoint demotion (regression guard for the
    silent undercount where the counter sat behind `if not dry_run`).
  * dry-run writes nothing.
  * live run relocates loose files + demotes the state payload to a pointer, and
    verify_no_legacy reports CLEAN afterwards.
  * idempotency: a second live run is a no-op.
"""
import importlib.util
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(mod):
    spec = importlib.util.spec_from_file_location(
        mod, os.path.join(ROOT, "tools", f"{mod}.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SP = _load("savepoint_migrate")


def _fixture(tmp_path):
    """A v4 spoke with one loose savepoint + a payload-style WAI-State._savepoint."""
    local = tmp_path / "WAI-Harness" / "spoke" / "local"
    (local / "initiatives").mkdir(parents=True)
    (local / "savepoints").mkdir(parents=True)
    (local / "WAI-State.json").write_text(json.dumps({"_savepoint": {
        "status": "pending", "lug_id": "x",
        "work_done": "did stuff", "work_context": "ctx", "resume_note": "go"}}))
    (local / "savepoints" / "sp-loose-1.json").write_text(
        json.dumps({"id": "sp-loose-1", "status": "completed"}))
    return str(tmp_path)


def test_dry_run_live_parity(tmp_path):
    a = _fixture(tmp_path / "a")
    b = _fixture(tmp_path / "b")
    dry = SP.migrate(a, dry_run=True)
    live = SP.migrate(b, dry_run=False)
    # 1 loose + 1 state-payload = 2 in BOTH modes (the regression this guards)
    assert dry["relocated"] == live["relocated"] == 2
    assert dry["relocated_active"] == live["relocated_active"]
    assert dry["relocated_terminal"] == live["relocated_terminal"]


def test_dry_run_writes_nothing(tmp_path):
    root = _fixture(tmp_path)
    SP.migrate(root, dry_run=True)
    spdir = tmp_path / "WAI-Harness" / "spoke" / "local" / "initiatives" / "savepoints"
    assert list(spdir.rglob("*.json")) == []


def test_live_migrate_then_clean(tmp_path):
    root = _fixture(tmp_path)
    rep = SP.migrate(root, dry_run=False)
    assert rep["ok"] and not rep["errors"]
    assert SP.verify_no_legacy(root)["clean"] is True
    # WAI-State._savepoint demoted to a pointer (no inline payload)
    sp = json.loads((tmp_path / "WAI-Harness" / "spoke" / "local" / "WAI-State.json")
                    .read_text())["_savepoint"]
    assert not ({"work_done", "work_context"} & set(sp))
    assert sp.get("canonical_path")


def test_done_status_variants_are_terminal(tmp_path):
    """A savepoint whose work is concluded must land in completed/ (not active),
    across the common status spellings — regression for 'complete'/'resolved'
    being mis-filed as active."""
    local = tmp_path / "WAI-Harness" / "spoke" / "local"
    (local / "initiatives").mkdir(parents=True)
    (local / "savepoints").mkdir(parents=True)
    (local / "WAI-State.json").write_text(json.dumps({}))
    for i, st in enumerate(["complete", "resolved", "done", "closed", "shelved", "superseded"]):
        (local / "savepoints" / f"sp-{st}-{i}.json").write_text(
            json.dumps({"id": f"sp-{st}-{i}", "status": st}))
    rep = SP.migrate(str(tmp_path), dry_run=False)
    assert rep["relocated_terminal"] == 6 and rep["relocated_active"] == 0
    active = list((local / "initiatives" / "savepoints").glob("*/*.json"))
    completed = list((local / "initiatives" / "savepoints").glob("*/completed/*.json"))
    assert len(active) == 0 and len(completed) == 6


def test_idempotent(tmp_path):
    root = _fixture(tmp_path)
    SP.migrate(root, dry_run=False)
    again = SP.migrate(root, dry_run=False)
    assert again["relocated"] == 0
    assert SP.verify_no_legacy(root)["clean"] is True


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            tp = Path(tempfile.mkdtemp())
            try:
                fn(tp)
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)
