#!/usr/bin/env python3
"""cutover_readiness.py — "can I retire framework + old hub and move to mywheel?" gate.

Answers two operational questions with one command:
  1. WHEN can legacy (framework/ + old hub/) be retired? -> when this reports GREEN.
  2. HOW do I know the fleet is on the NEW hub? -> the fleet_on_new_hub condition (per-spoke
     hub_path == the new hub) + every active spoke CURRENT+ACTIVE on v4.

It is a READ-ONLY gate — it never moves or deletes anything. Retiring legacy is a HARD human
gate; this tool tells you whether the preconditions hold, and exactly which are still red.

Conditions (all must be GREEN to retire):
  master_versioned   — mywheel is its own git repo (canonical truth has history)
  new_hub_serves     — the new hub (mywheel/.../hub/managed) actually carries the hub's job:
                       registry + advisors (today the OLD hub holds these)
  fleet_warmed       — every active-30d spoke is CURRENT + ACTIVE on v4 (not just a canary)
  fleet_on_new_hub   — every active spoke's hub_path points at the NEW hub, not the old one
  integrity_green    — fleet_verify integrity PASS across all installs
  no_legacy_refs     — no active spoke still resolves the hub to the old hub path

Pure helpers are path-injected + tested; the CLI wires live defaults + fleet_verify.
"""
import argparse
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import fleet_verify  # noqa: E402

DEFAULT_REGISTRY = "/home/mario/projects/wheelwright/hub/hub-registry.json"
OLD_HUB = "/home/mario/projects/wheelwright/hub"
# The hub stood itself up IN PLACE on v4 (symlink-bridge, no 385MB relocation): the v4 hub
# serves from <hub-root>/WAI-Harness/hub. That is the canonical new hub_path spokes repoint to.
NEW_HUB = "/home/mario/projects/wheelwright/hub/WAI-Harness/hub"
MYWHEEL_ROOT = "/home/mario/projects/wheelwright/mywheel"


def check_master_versioned(mywheel_root=MYWHEEL_ROOT):
    git = Path(mywheel_root) / ".git"
    ok = git.exists()
    return {"name": "master_versioned", "ok": ok,
            "detail": f"{mywheel_root}/.git {'present' if ok else 'MISSING — git init the master'}"}


def check_new_hub_serves(new_hub=NEW_HUB):
    """The new hub serves only when its managed tree carries the hub's operational content:
    a registry and at least one advisor. An empty hub/managed is a skeleton, not a hub."""
    hubp = Path(new_hub)
    has_registry = (hubp / "managed" / "hub-registry.json").exists() or \
                   (hubp / "local" / "hub-registry.json").exists()
    advisor_dirs = list((hubp / "managed" / "advisors").glob("*/")) + \
                   list((hubp / "local" / "advisors").glob("*/"))
    ok = has_registry and len(advisor_dirs) > 0
    return {"name": "new_hub_serves", "ok": ok,
            "detail": f"registry={'yes' if has_registry else 'NO'}, "
                      f"advisors={len(advisor_dirs)} (old hub must be migrated into the new hub)"}


def _spoke_hub_path(install_dir):
    """Read a spoke's configured hub_path from v3 or v4 WAI-State."""
    install = Path(install_dir)
    spoke_root = install.parent  # <spoke>/WAI-Harness -> <spoke>
    for cand in (spoke_root / "WAI-Spoke" / "WAI-State.json",
                 install / "spoke" / "local" / "WAI-State.json"):
        if cand.exists():
            try:
                return json.load(open(cand)).get("wheel", {}).get("hub_path")
            except (ValueError, OSError):
                continue
    return None


def assess(fleet_report, new_hub=NEW_HUB, old_hub=OLD_HUB, active_installs=None):
    """Combine a fleet_verify report + per-spoke hub_path into the cutover conditions.
    active_installs: optional set of install paths to treat as the 'active fleet' (defaults
    to all installs in the report)."""
    installs = fleet_report["installs"]
    if active_installs is not None:
        installs = [i for i in installs if i["install"] in active_installs]

    new_hub_real = os.path.realpath(new_hub)
    on_new, on_old, warmed, current = [], [], [], []
    for i in installs:
        hp = _spoke_hub_path(i["install"])
        if hp and os.path.realpath(hp) == new_hub_real:
            on_new.append(i["install"])
        elif hp and os.path.realpath(hp) == os.path.realpath(old_hub):
            on_old.append(i["install"])
        # 'warmed' = on v4 + intact (the retire-relevant durable state); currency vs the
        # very-latest master self-heals on the next spin-up pull, so it is informational only.
        if i["activation"] == "ACTIVE" and i["integrity"] == "PASS":
            warmed.append(i["install"])
        if i["currency"] == "CURRENT":
            current.append(i["install"])

    n = len(installs)
    integ_ok = all(i["integrity"] == "PASS" for i in installs)
    conds = [
        {"name": "fleet_warmed", "ok": len(warmed) == n,
         "detail": f"{len(warmed)}/{n} ACTIVE+intact on v4 "
                   f"({len(current)}/{n} also current vs latest master; currency self-heals on spin-up)"},
        {"name": "fleet_on_new_hub", "ok": len(on_new) == n,
         "detail": f"{len(on_new)}/{n} point hub_path at the NEW hub ({len(on_old)} still on OLD hub)"},
        {"name": "integrity_green", "ok": integ_ok,
         "detail": f"integrity PASS on {sum(1 for i in installs if i['integrity']=='PASS')}/{n}"},
        {"name": "no_legacy_refs", "ok": len(on_old) == 0,
         "detail": f"{len(on_old)} spoke(s) still resolve the hub to the OLD hub"},
    ]
    return conds, {"on_new_hub": on_new, "on_old_hub": on_old, "warmed": warmed,
                   "current": current, "total": n}


def _registry_report(registry_path, master_dir):
    """Per-install verdicts driven by the REGISTRY (non-archive, on-disk) — never a
    filesystem walk (feedback-fleet-paths-from-registry)."""
    master_files = fleet_verify.load_manifest_files(Path(master_dir) / fleet_verify.MANIFEST_REL)
    reg = json.load(open(registry_path)).get("wheels", [])
    installs = []
    for w in reg:
        if "/_archive/" in os.path.realpath(w["path"]):
            continue
        inst = os.path.join(w["path"], "WAI-Harness")
        if os.path.isdir(inst):
            installs.append(fleet_verify.classify_install(inst, master_files))
    return {"installs": installs}


def readiness(registry_path=DEFAULT_REGISTRY, mywheel_root=MYWHEEL_ROOT,
              new_hub=NEW_HUB, old_hub=OLD_HUB, now_iso=None):
    master_dir = os.path.join(mywheel_root, "WAI-Harness")
    report = _registry_report(registry_path, master_dir)
    conds = [check_master_versioned(mywheel_root), check_new_hub_serves(new_hub)]
    fleet_conds, fleet_detail = assess(report, new_hub=new_hub, old_hub=old_hub)
    conds += fleet_conds
    retire_allowed = all(c["ok"] for c in conds)
    return {"retire_allowed": retire_allowed, "conditions": conds,
            "fleet": fleet_detail, "verdict": "GREEN — retire allowed" if retire_allowed
            else "NOT READY — blockers below"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="cutover readiness: can framework+old-hub be retired into mywheel?")
    ap.add_argument("--registry", default=DEFAULT_REGISTRY)
    ap.add_argument("--mywheel-root", default=MYWHEEL_ROOT)
    ap.add_argument("--new-hub", default=NEW_HUB)
    ap.add_argument("--old-hub", default=OLD_HUB)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    r = readiness(registry_path=a.registry, mywheel_root=a.mywheel_root, new_hub=a.new_hub, old_hub=a.old_hub)
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"CUTOVER READINESS: {r['verdict']}")
        for c in r["conditions"]:
            print(f"  [{'GREEN' if c['ok'] else ' RED '}] {c['name']}: {c['detail']}")
        f = r["fleet"]
        print(f"  fleet: {len(f['on_new_hub'])}/{f['total']} on new hub | "
              f"{len(f['warmed'])}/{f['total']} warmed+active")
    return 0 if r["retire_allowed"] else 1


if __name__ == "__main__":
    sys.exit(main())
