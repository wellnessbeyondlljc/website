#!/usr/bin/env python3
"""Verification test for impl-v4-harness-skeleton-v1 (test-at-birth).

Covers verify[]: master tree exists (spoke managed/local/ozi/advisors + hub
managed/local), all declared subfolders present with .gitkeep, MANIFEST scaffold
valid, manifest build + --verify (zero mismatches clean / exactly one on edit),
idempotent re-run, and the additive property (legacy trees untouched — the tool
only writes under the given mywheel path).
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


SK = _load("v4_skeleton")
MB = _load("manifest_build")


def test_master_tree_and_subfolders_exist():
    with tempfile.TemporaryDirectory() as d:
        SK.scaffold(d)
        spoke = os.path.join(d, "WAI-Harness", "spoke")
        hub = os.path.join(d, "WAI-Harness", "hub")
        for top in ("managed", "local", "ozi", "advisors"):
            assert os.path.isdir(os.path.join(spoke, top)), f"spoke/{top} missing"
        for sub in ("managed", "local"):
            assert os.path.isdir(os.path.join(hub, sub)), f"hub/{sub} missing"
        # every declared managed/local subfolder exists with a .gitkeep
        for sub in SK.MANAGED_SUBDIRS:
            leaf = os.path.join(spoke, "managed", sub)
            assert os.path.isdir(leaf) and os.path.exists(os.path.join(leaf, ".gitkeep")), sub
        for sub in SK.LOCAL_SUBDIRS:
            leaf = os.path.join(spoke, "local", sub)
            assert os.path.isdir(leaf) and os.path.exists(os.path.join(leaf, ".gitkeep")), sub


def test_manifest_scaffold_valid():
    with tempfile.TemporaryDirectory() as d:
        res = SK.scaffold(d)
        m = json.load(open(res["manifest"]))
        assert m["harness_version"] and m["is_master"] is True and "files" in m


def test_manifest_build_and_verify_detects_edit():
    with tempfile.TemporaryDirectory() as d:
        SK.scaffold(d)
        managed = os.path.join(d, "WAI-Harness", "spoke", "managed")
        # seed a managed file so the manifest has real content to protect
        target = os.path.join(managed, "tools", "x.py")
        open(target, "w").write("print('v1')\n")
        m = MB.build(managed, now_iso="2026-06-09T00:00:00Z")
        assert "tools/x.py" in m["files"] and m["files"]["tools/x.py"]["md5"]
        # clean tree -> zero mismatches
        v0 = MB.verify(managed)
        assert v0["ok"] and not v0["mismatches"], v0
        # an unauthorized edit to a managed file -> exactly that mismatch
        open(target, "w").write("print('TAMPERED')\n")
        v1 = MB.verify(managed)
        assert v1["mismatches"] == ["tools/x.py"], v1
        assert not v1["ok"]


def test_skeleton_idempotent():
    with tempfile.TemporaryDirectory() as d:
        first = SK.scaffold(d)
        assert len(first["created"]) > 0
        second = SK.scaffold(d)  # re-run: no error, nothing new created
        assert second["created"] == [], "re-run must be idempotent (no duplication)"


def test_additive_only_writes_under_given_path():
    with tempfile.TemporaryDirectory() as d:
        sentinel = os.path.join(d, "legacy_untouched.txt")
        open(sentinel, "w").write("legacy")
        SK.scaffold(os.path.join(d, "mywheel"))
        # the tool only created under mywheel/; the sibling legacy file is intact
        assert open(sentinel).read() == "legacy"
        assert os.path.isdir(os.path.join(d, "mywheel", "WAI-Harness"))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASS")
