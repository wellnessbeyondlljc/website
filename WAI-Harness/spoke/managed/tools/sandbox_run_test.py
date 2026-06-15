#!/usr/bin/env python3
"""sandbox_run_test.py — run a generated verification test in an ISOLATED runtime.

Part of the execution sandbox (impl-execution-sandbox-foundation-v1). A
generated/AC-derived test must never run against live harness state: a DROP, a
runaway write, or a flaky test could corrupt the very substrate the
verification + observability spines depend on. So the test runs against a
SCRATCH copy of harness.db (exposed via env WAI_HARNESS_DB) inside an isolated
runtime (a git worktree from the concurrency primitive when one exists, else a
temp dir). The live tree and live harness.db are never touched.

The runner also classifies the outcome so the dispatcher routes correctly and
NEVER escalation-storms on a bad test:
  - test-defect  : the test errors on RUN (syntax/collection/setup) -> route to QA
  - flaky        : runs but non-deterministic across N runs        -> quarantine + QA
  - code-failure : runs deterministically and asserts false        -> the real signal
  - pass         : runs deterministically and asserts true
None of these hard-halt the queue.

Threat-model note (scale path, NOT built here): for multi-tenant / untrusted
agents, replace the worktree+scratch-DB isolation with a container or WASM
sandbox per agent. Single-user-local trust makes that unnecessary for v1 — the
realistic failure is accidental destruction, not an adversary.

API:
  run_test(test_path, live_db=None, runs=3, repo_path=".", session_id=None)
      -> {"result": 1|0|None, "classification": str, "route": str|None,
          "evidence": {...}, "live_db_intact": bool}
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    import worktree_guard
except ImportError:
    worktree_guard = None

EXIT = {"pass": 0, "code-failure": 1, "flaky": 3, "test-defect": 4}


def _sha(path):
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_once(test_path, scratch_db, cwd):
    env = dict(os.environ)
    if scratch_db:
        env["WAI_HARNESS_DB"] = scratch_db
    r = subprocess.run([sys.executable, "-m", "pytest", test_path, "-q", "-p", "no:cacheprovider"],
                       cwd=cwd, env=env, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def _is_collection_error(rc, out):
    # pytest: rc 2 = collection/usage error; "errors during collection" / "ERROR" in a
    # broken test file. rc 5 = no tests collected (also a defective test artifact).
    return rc in (2, 3, 5) or "errors during collection" in out.lower()


def run_test(test_path, live_db=None, runs=3, repo_path=".", session_id=None):
    before = _sha(live_db)
    run_dir = repo_path
    if worktree_guard and session_id:
        run_dir = worktree_guard.get_worktree(session_id, repo_path=repo_path)

    with tempfile.TemporaryDirectory(prefix="sandbox-") as tmp:
        def fresh_scratch():
            # each isolated run gets a CLEAN copy of the live db, so a test that
            # mutates state (DROP/INSERT) is not misread as flaky across runs.
            if live_db and os.path.exists(live_db):
                sdb = os.path.join(tmp, "scratch-harness.db")
                shutil.copy2(live_db, sdb)
                return sdb
            return None

        # first run decides defect vs runnable
        rc0, out0 = _run_once(test_path, fresh_scratch(), run_dir)
        if _is_collection_error(rc0, out0):
            result = {"result": None, "classification": "test-defect", "route": "QA",
                      "evidence": {"reason": "test errors on run (syntax/collection/setup)",
                                   "exit": rc0, "tail": out0[-400:]}}
            result["live_db_intact"] = (_sha(live_db) == before)
            return result

        outcomes = ["pass" if rc0 == 0 else "fail"]
        for _ in range(1, max(1, runs)):
            rc, _o = _run_once(test_path, fresh_scratch(), run_dir)
            outcomes.append("pass" if rc == 0 else "fail")

        distinct = set(outcomes)
        if len(distinct) > 1:
            cls, result_val, route = "flaky", None, "QA"
        elif distinct == {"pass"}:
            cls, result_val, route = "pass", 1, None
        else:
            cls, result_val, route = "code-failure", 0, None

        result = {"result": result_val, "classification": cls, "route": route,
                  "evidence": {"outcomes": outcomes, "tail": out0[-400:]}}
        result["live_db_intact"] = (_sha(live_db) == before)
        return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="run a generated verification test in isolation")
    ap.add_argument("test_path")
    ap.add_argument("--live-db", default=None)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--repo-path", default=".")
    ap.add_argument("--session-id", default=None)
    a = ap.parse_args(argv)
    res = run_test(a.test_path, a.live_db, a.runs, a.repo_path, a.session_id)
    print(json.dumps(res))
    return EXIT.get(res["classification"], 1)


if __name__ == "__main__":
    sys.exit(main())
