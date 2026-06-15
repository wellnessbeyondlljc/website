#!/usr/bin/env python3
"""Verification test for impl-execution-sandbox-foundation-v1 (test-at-birth).

Covers verify[]: isolated test run (live DB byte-identical), atomic write
(discard-on-fail / commit-on-pass), scope fence (out-of-scope flagged not
applied), flaky vs test-defect vs code-failure classification, and delivery of
the protected-paths guard rule to Basher (the .claude/ hook is Basher-owned).
"""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "tools", f"{mod}.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _build(db):
    r = subprocess.run([sys.executable, "tools/create_harness_db.py", "--db-path", db],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_isolated_test_run_leaves_live_db_intact():
    srt = _load("sandbox_run_test")
    with tempfile.TemporaryDirectory() as d:
        live = os.path.join(d, "live.db"); _build(live)
        before = open(live, "rb").read()
        # a "generated" test that DROPs a table in WHATEVER db it is given
        t = os.path.join(d, "test_drop.py")
        open(t, "w").write(
            "import os, sqlite3\n"
            "def test_drop():\n"
            "    db = os.environ['WAI_HARNESS_DB']\n"
            "    con = sqlite3.connect(db); con.execute('DROP TABLE checks'); con.commit(); con.close()\n"
            "    assert True\n")
        res = srt.run_test(t, live_db=live, runs=2)
        assert res["classification"] == "pass", res
        assert res["live_db_intact"] is True, "live db must be byte-identical"
        assert open(live, "rb").read() == before, "live db bytes changed!"
        # the live db still has the checks table (only the scratch copy was dropped)
        con = sqlite3.connect(live)
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "checks" in names; con.close()


def test_atomic_write_discards_on_invalid_commits_on_valid():
    aw = _load("atomic_write")
    with tempfile.TemporaryDirectory() as d:
        target = os.path.join(d, "mod.py")
        open(target, "w").write("# original\n")
        orig = open(target).read()
        # invalid python -> discarded, live unchanged, no .staging left behind
        bad = aw.atomic_write(target, "def broken(:\n    pass\n")
        assert bad["committed"] is False
        assert open(target).read() == orig, "live target must be unchanged on failure"
        assert not [f for f in os.listdir(d) if f.startswith(".staging")], "no partial write"
        # valid python -> committed atomically
        ok = aw.atomic_write(target, "def fine():\n    return 1\n")
        assert ok["committed"] is True
        assert "def fine" in open(target).read()
        # invalid json discarded too
        jt = os.path.join(d, "x.json")
        open(jt, "w").write('{"a":1}')
        assert aw.atomic_write(jt, "{not json")["committed"] is False
        assert open(jt).read() == '{"a":1}'


def test_scope_fence_flags_out_of_scope_writes():
    sf = _load("scope_fence")
    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, "bytype", "implementation", "open")
        os.makedirs(root)
        lug = {"id": "impl-demo-v1", "file_targets": ["tools/foo.py", "tools/bar.py"]}
        json.dump(lug, open(os.path.join(root, "impl-demo-v1.json"), "w"))
        lr = os.path.join(d, "bytype")
        inb = sf.check_scope("impl-demo-v1", "tools/foo.py", lugs_root=lr)
        assert inb["in_scope"] and not inb["flagged"]
        out = sf.check_scope("impl-demo-v1", "tools/evil.py", lugs_root=lr)
        assert out["flagged"] and not out["in_scope"], "out-of-scope write must be flagged"
        # unknown lug fails closed
        unk = sf.check_scope("impl-missing-v1", "tools/foo.py", lugs_root=lr)
        assert unk["flagged"] and not unk["lug_found"]


def test_classifies_test_defect_distinct_from_code_failure():
    srt = _load("sandbox_run_test")
    with tempfile.TemporaryDirectory() as d:
        # syntactically broken test -> test-defect (route QA), NOT code-failure
        bad = os.path.join(d, "test_broken.py")
        open(bad, "w").write("def test_x(:\n    pass\n")
        rb = srt.run_test(bad, runs=3)
        assert rb["classification"] == "test-defect", rb
        assert rb["route"] == "QA" and rb["result"] is None
        # a real assertion failure -> code-failure (the genuine signal)
        fail = os.path.join(d, "test_fail.py")
        open(fail, "w").write("def test_y():\n    assert False\n")
        rf = srt.run_test(fail, runs=3)
        assert rf["classification"] == "code-failure" and rf["result"] == 0, rf


def test_classifies_flaky_after_repeated_runs():
    srt = _load("sandbox_run_test")
    with tempfile.TemporaryDirectory() as d:
        # a test that alternates pass/fail across runs via a sibling counter file
        t = os.path.join(d, "test_flaky.py")
        open(t, "w").write(
            "import os\n"
            "def test_alt():\n"
            "    c = __file__ + '.count'\n"
            "    n = int(open(c).read()) if os.path.exists(c) else 0\n"
            "    n += 1; open(c, 'w').write(str(n))\n"
            "    assert n % 2 == 0\n")
        res = srt.run_test(t, runs=3)
        assert res["classification"] == "flaky", res
        assert res["route"] == "QA" and res["result"] is None


def test_protected_paths_guard_rule_delivered_to_basher():
    """The .claude/ hook is Basher-owned; framework authors the RULE and delivers
    it. Verify the outgoing delivery lug names the protected paths."""
    p = os.path.join(ROOT, "WAI-Spoke/lugs/outgoing/impl-basher-v4-claude-touchpoints-v1.json")
    assert os.path.exists(p), "the .claude touchpoints delivery lug to Basher must exist"
    d = json.load(open(p))
    blob = json.dumps(d).lower()
    assert "harness.db" in blob and "journal" in blob and "managed/" in blob
    assert d.get("routed_to") == "basher"
    assert d.get("delivered_at"), "delivery must be stamped (deliver immediately, not at closeout)"
    # framework authors the RULE: the exact guard snippet must travel with the lug
    snippet = d.get("guard_rule_snippet", "")
    assert "harness.db" in snippet and ("rm" in snippet or "truncate" in snippet), \
        "exact framework-authored guard snippet must be embedded for a cold-reader Basher"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"PASS {name}")
    print("ALL PASS")
