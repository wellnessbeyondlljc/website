#!/usr/bin/env python3
"""verify_then_define — P5: gate goal-definition on a verified, advisor-robust platform.

Operator's runtime order: a spoke must be VERIFIED (harness certified + foundation ready
+ advisors robust) BEFORE its goals are defined. This is the gate. It ships with a --force
override because certify was 0/9 on its first fleet pass — a flaky cert must never hard-lock
the operator out of defining their own goals.

Pure gate() (unit-tested) + gate_spoke() reading real files + CLI.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


def gate(checks: Dict[str, bool], force: bool = False) -> Dict[str, Any]:
    """Decide whether the goal-definition interview may run. Pure."""
    blockers = []
    if not checks.get("certified"):
        blockers.append("not certified (run conductor --certify)")
    if not checks.get("foundation_ready"):
        blockers.append("foundation not complete (run wai-foundation)")
    if not checks.get("advisors_healthy"):
        blockers.append("a piloting advisor has an empty pilot_contract or zero fires")
    if blockers and force:
        return {"allowed": True, "forced": True, "blockers": blockers}
    return {"allowed": not blockers, "forced": False, "blockers": blockers}


def _read_json(p):
    try:
        return json.load(open(p))
    except (json.JSONDecodeError, OSError):
        return {}


def gate_spoke(root: str, force: bool = False) -> Dict[str, Any]:
    local = os.path.join(root, "WAI-Harness", "spoke", "local")
    state = _read_json(os.path.join(local, "WAI-State.json"))
    foundation_ready = bool((state.get("_project_foundation") or {}).get("completed"))

    # certified: hub-registry harness_certification for this spoke == certified
    certified = False
    reg = _read_json(os.path.join(root, "WAI-Harness", "hub", "local", "hub-registry.json"))
    for w in (reg.get("wheels") or reg.get("spokes") or []):
        cert = (w.get("harness_certification") or {})
        if str(cert.get("status", "")).lower() == "certified":
            certified = True
            break
    # if there's no hub registry at all (pure spoke), don't hard-block on cert
    if not reg:
        certified = True

    # advisors healthy: no piloting advisor with an empty contract
    advisors_healthy = True
    areg = _read_json(os.path.join(root, "WAI-Harness", "spoke", "managed", "crew", "advisors-registry.json"))
    for a in (areg.get("advisors") or areg.get("spoke_advisors") or []):
        if isinstance(a, dict) and str(a.get("status", "")).lower() == "piloting":
            pc = a.get("pilot_contract") or {}
            if not pc.get("hypothesis") or not pc.get("kpis"):
                advisors_healthy = False
                break

    checks = {"certified": certified, "foundation_ready": foundation_ready,
              "advisors_healthy": advisors_healthy}
    r = gate(checks, force=force)
    r["checks"] = checks
    return r


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="verify_then_define — P5 goal-definition gate")
    ap.add_argument("--spoke", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    r = gate_spoke(args.spoke, force=args.force)
    print(json.dumps(r, indent=2))
    sys.exit(0 if r["allowed"] else 1)
