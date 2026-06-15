#!/usr/bin/env python3
"""closeout_ac_gate.py — the closeout hard gate that keeps the epic honest
(impl-v4-prevent-state-decay-hardening-v1, AC2).

The S45 episode happened because two things were never gated at closeout:
  1. Epic AC checkboxes could drift from lug evidence (20 ACs marked done, 0 evidence).
  2. A parent_epic lug could complete without recording closes_epic_acs (the linkage
     the epic derives status from), so the drift was invisible.

This gate, run at closeout, blocks the session from closing while EITHER holds:
  - DRIFT: any open epic has AC checkbox-vs-evidence drift (reconcile_epic_acs).
  - UNLINKED: any completed parent_epic lug has no closes_epic_acs / a bare full claim
    (verification_spine.completion_gate).

Non-zero exit = closeout must stop and the agent must reconcile (flip boxes / link lugs)
before completing. Pure-ish: read_* scan the tree; CLI wraps with IO + exit code.
"""
import argparse
import glob
import importlib.util
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import wai_paths


def _load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(_HERE, f"{mod}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def check_drift(spoke_path="."):
    rec = _load("reconcile_epic_acs")
    drift = rec.read_ac_drift(spoke_path)
    offenders = {e: d for e, d in drift.items() if d.get("total_drift", 0) > 0}
    return {"ok": not offenders, "drift_by_epic": offenders}


def _open_epic_ids(spoke):
    ids = set()
    for status in ("open", "in_progress"):
        for f in glob.glob(os.path.join(spoke, "lugs", "bytype", "epic", status, "*.json")):
            try:
                ids.add(json.load(open(f)).get("id"))
            except (OSError, json.JSONDecodeError):
                continue
    return ids


def check_completion_linkage(spoke_path="."):
    """Enforce AC-linkage for completed lugs under an OPEN epic only. Forward-enforcement
    where it matters (epics we are actively tracking); closed-epic history is out of scope
    (relitigating every ancient epic would make closeout permanently un-passable). A lug
    that closes no AC must say so via closes_no_ac (handled in completion_gate)."""
    vs = _load("verification_spine")
    base, _ = wai_paths.resolve_wai_root(spoke_path)
    spoke = base or (spoke_path if os.path.basename(spoke_path) == "WAI-Spoke" else os.path.join(spoke_path, "WAI-Spoke"))
    open_epics = _open_epic_ids(spoke)
    violations = []
    for f in glob.glob(os.path.join(spoke, "lugs", "bytype", "**", "*.json"), recursive=True):
        if "/completed/" not in f and "/done/" not in f:
            continue
        try:
            lug = json.load(open(f))
        except (OSError, json.JSONDecodeError):
            continue
        if lug.get("status") not in ("completed", "done"):
            continue
        parent = lug.get("parent_epic") or lug.get("epic")
        if parent not in open_epics:   # only enforce active (open) epics
            continue
        verdict = vs.completion_gate(lug)
        if not verdict["ok"]:
            violations.append({"lug": lug.get("id") or os.path.basename(f),
                               "reasons": verdict["reasons"]})
    return {"ok": not violations, "violations": violations}


def run(spoke_path="."):
    drift = check_drift(spoke_path)
    linkage = check_completion_linkage(spoke_path)
    return {"ok": drift["ok"] and linkage["ok"], "drift": drift, "linkage": linkage}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--spoke-path", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    res = run(args.spoke_path)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        if res["ok"]:
            print("closeout AC gate: PASS (no epic drift, all completed epic-lugs linked)")
        else:
            print("closeout AC gate: BLOCKED")
            for e, d in res["drift"]["drift_by_epic"].items():
                print(f"  DRIFT {e}: {d}")
            for v in res["linkage"]["violations"]:
                print(f"  UNLINKED {v['lug']}: {'; '.join(v['reasons'])}")
            print("  -> reconcile (tools/reconcile_epic_acs.py) + add closes_epic_acs before closing.")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
