#!/usr/bin/env python3
"""promote_lug.py — the draft->open promotion gate (AC11 cold-reader hook + AC12 test-at-birth).

Authoring (new_lug.build_v4_lug) refuses to write a draft missing title/situation, and
validate_lug_v4 enforces the full v4 structural schema (mandatory context, rev, a
verification_test per AC). What was missing is the PROMOTION gate: a lug must not move
draft->open until its verification_test has actually been RUN and PASSED, and that run is
recorded on the lug (test_result_history) so a later reader sees the evidence, not just the
intent.

promotion_gate(lug)        -> {ok, failures}: structural (validate_lug_v4) + every
                              verification_test result == 1 (1=pass, 0=fail, None=not-run).
record_test_run(lug, ...)  -> append a {ts, mode, result, version, covers} entry to
                              lug['test_result_history'] (the AC12 execution history).
promote(lug, ...)          -> if the gate passes: stamp a summary run into test_result_history,
                              set status='open', bump updated_at; else return failures, no flip.

Pure + injectable. The cold-reader half of AC11 (object-quality prose gate) runs in the
lug-reviewer subagent (.claude) — a Basher distribution; this module is the machine gate.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import validate_lug_v4 as v4  # noqa: E402

PASS = 1  # validate_lug_v4._VALID_RESULTS = {1, 0, None}


def _tests(lug):
    vt = lug.get("verification_test")
    return vt if isinstance(vt, list) else []


def promotion_gate(lug, spoke_root="."):
    """Return {ok, failures}. A lug may go draft->open only if it passes the v4 structural
    schema AND every verification_test has been run and passed (result == 1)."""
    failures = []
    structural = v4.validate_lug_v4(lug, spoke_root=spoke_root)
    if not structural.get("ok"):
        failures.extend(structural.get("failures", []))
    tests = _tests(lug)
    if not tests:
        failures.append("no verification_test — test-at-birth bars draft->open")
    for i, t in enumerate(tests):
        if not isinstance(t, dict):
            failures.append(f"verification_test[{i}] not an object")
            continue
        res = t.get("result")
        if res is None:
            failures.append(f"verification_test[{i}] not run yet (result=None) — "
                            "run it and record the result before promotion")
        elif res != PASS:
            failures.append(f"verification_test[{i}] failing (result={res!r}) — "
                            "promotion requires a passing run")
    return {"ok": not failures, "failures": failures}


def record_test_run(lug, mode, result, now_iso, version=None, covers=None):
    """Append one run to lug['test_result_history'] (created if absent). Returns the entry."""
    entry = {"ts": now_iso, "mode": mode, "result": result, "version": version}
    if covers is not None:
        entry["covers"] = covers
    lug.setdefault("test_result_history", []).append(entry)
    return entry


def promote(lug, now_iso, version=None, spoke_root="."):
    """Promote a draft lug to open IFF the gate passes. On success: record a summary run in
    test_result_history, set status='open', bump updated_at. Returns {ok, lug?, failures?}."""
    gate = promotion_gate(lug, spoke_root=spoke_root)
    if not gate["ok"]:
        return {"ok": False, "failures": gate["failures"]}
    tests = _tests(lug)
    covers = sorted({c for t in tests for c in ([t.get("covers_ac")] if t.get("covers_ac") else [])})
    record_test_run(lug, mode="promotion-gate", result=PASS, now_iso=now_iso,
                    version=version, covers=covers or None)
    lug["status"] = "open"
    lug["updated_at"] = now_iso
    return {"ok": True, "lug": lug}
