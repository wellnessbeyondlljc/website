#!/usr/bin/env python3
"""Verification test for impl-v4-migration-engine-v1 (test-at-birth).

Covers verify[]: reads home map as data, no-orphan gate (synthetic unmapped folder
fails; removing it passes), bucket routing (Preserve copy+checksum; Flag staged not
placed; Drop untouched / --confirm-drop moves to trash never rm), additive (source
intact), survey precondition, bootstrap + adopt dry-run plans, idempotent execute,
and dry-run writes nothing.
"""
import importlib.util
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


MG = _load("v4_migrate")
SPEC = os.path.join(ROOT, "WAI-Spoke/lugs/bytype/spec/open/spec-v4-migration-home-map-v1.json")


def test_reads_home_map_as_data():
    hm = MG.load_home_map(SPEC)
    assert isinstance(hm, list) and len(hm) > 10
    assert all("category" in r and "bucket" in r and "home" in r for r in hm)
    assert {r["bucket"] for r in hm} <= {"Preserve", "Transform", "Flag", "Drop"}


def test_no_orphan_gate_fails_on_unmapped_then_passes():
    hm = MG.load_home_map(SPEC)
    with tempfile.TemporaryDirectory() as d:
        # claimed categories from the map
        for name in ("lugs", "sessions", "teachings"):
            os.makedirs(os.path.join(d, name))
        open(os.path.join(d, "WAI-State.json"), "w").write("{}")
        # an UNMAPPED folder -> orphan
        os.makedirs(os.path.join(d, "xyzzy_unmapped"))
        rep = MG.dry_run_upgrade(d, hm)
        assert "xyzzy_unmapped" in rep["orphans"], rep["orphans"]
        assert rep["ok"] is False, "no-orphan gate must fail the dry-run"
        # remove the orphan -> passes
        os.rmdir(os.path.join(d, "xyzzy_unmapped"))
        rep2 = MG.dry_run_upgrade(d, hm)
        assert rep2["ok"] is True and rep2["orphans"] == []
        assert rep2["wrote"] is False, "dry-run writes nothing"


def test_bucket_routing_preserve_flag_drop():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "src"); os.makedirs(src)
        # a Preserve dir with a file
        pres = os.path.join(src, "lugs"); os.makedirs(pres)
        open(os.path.join(pres, "a.json"), "w").write('{"x":1}')
        target = os.path.join(d, "WAI-Harness")
        # Preserve -> copied with checksum, source intact
        r = MG.execute_category({"category": "lugs/", "bucket": "Preserve", "home": "spoke/local/lugs"},
                                pres, target)
        assert r["copied"] == 1 and r["checksums"]
        assert os.path.exists(os.path.join(target, "spoke/local/lugs/a.json"))
        assert os.path.exists(os.path.join(pres, "a.json")), "additive: source intact"
        # Flag -> staged to .flagged/, NOT placed
        flagd = os.path.join(src, "signals"); os.makedirs(flagd)
        open(os.path.join(flagd, "s.json"), "w").write("{}")
        rf = MG.execute_category({"category": "signals/", "bucket": "Flag", "home": "spoke/local/signals"},
                                 flagd, target)
        assert rf["placed"] is False and os.path.exists(os.path.join(target, "spoke/.flagged/signals/s.json"))
        # Drop -> untouched by execute
        rd = MG.execute_category({"category": ".autosave/", "bucket": "Drop", "home": "trash"},
                                 os.path.join(src, "nope"), target)
        assert rd.get("skipped") or rd.get("untouched")


def test_confirm_drop_moves_to_trash_never_rm():
    with tempfile.TemporaryDirectory() as d:
        cat = os.path.join(d, "deadthing"); os.makedirs(cat)
        open(os.path.join(cat, "old.txt"), "w").write("stale")
        trash = os.path.join(d, "trash")
        dest = MG.confirm_drop(cat, trash_root=trash, rel="framework/deadthing")
        assert not os.path.exists(cat), "source moved out"
        assert os.path.exists(os.path.join(dest, "old.txt")), "present in trash (moved, not rm)"


def test_survey_precondition():
    with tempfile.TemporaryDirectory() as d:
        assert MG.has_current_survey(d) is False
        open(os.path.join(d, MG.SURVEY_NAME), "w").write("{}")
        assert MG.has_current_survey(d) is True


def test_bootstrap_and_adopt_dryrun_write_nothing():
    with tempfile.TemporaryDirectory() as d:
        mw = os.path.join(d, "mywheel")
        os.makedirs(os.path.join(mw, "WAI-Harness", "spoke", "managed", "tools"))
        b = MG.dry_run_bootstrap(mw)
        assert b["wrote"] is False and "tools" in b["blueprint_dirs"]
        assert "hub_registry_registration" in b
        a = MG.dry_run_adopt(d, MG.load_home_map(SPEC))
        assert a["wrote"] is False and a["gap_report"] and a["alignment_roadmap"]


def test_execute_is_idempotent_checksum():
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "lugs"); os.makedirs(src)
        open(os.path.join(src, "a.json"), "w").write('{"x":1}')
        target = os.path.join(d, "WAI-Harness")
        row = {"category": "lugs/", "bucket": "Preserve", "home": "spoke/local/lugs"}
        r1 = MG.execute_category(row, src, target)
        r2 = MG.execute_category(row, src, target)
        # same checksums both runs (re-copy is safe, no corruption)
        assert r1["checksums"] == r2["checksums"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASS")
