#!/usr/bin/env python3
"""fleet_dashboard.py — Fleet Status "christmas tree" dashboard (AC18, Stream J).

A per-spoke capability/health board across the whole fleet. CRUCIALLY, the spoke list comes
from hub-registry.json (the authoritative roster) — NEVER a filesystem walk, and _archive
wheels are excluded (lesson: feedback-fleet-paths-from-registry). For each registry spoke it
shows a row of status "lights": integrity / currency (vs master) / activation / on-disk —
plus Pattern Monitor (first-attempt approval rate + open halt count) when a spoke's
patterns/gate-log is present.

Pure core (build_fleet_dashboard) is injected with the registry + master so it is testable;
the CLI wires live defaults and reuses fleet_verify.classify_install for the per-spoke verdict.

Exit: 0 always (a dashboard reports state, it doesn't gate).
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
DEFAULT_MASTER = "/home/mario/projects/wheelwright/mywheel/WAI-Harness"
LIGHT = {True: "●", False: "○", None: "—"}   # on / off / n-a


def _registry_spokes(registry_path):
    """Authoritative, non-archive spokes from the registry: [{wheel_id, path}]."""
    reg = json.load(open(registry_path)).get("wheels", [])
    return [{"wheel_id": w["wheel_id"], "path": w["path"]}
            for w in reg if "/_archive/" not in os.path.realpath(w["path"])]


def _pattern_monitor(install_dir):
    """First-attempt approval rate + open-halt count from a spoke's gate-log, if present."""
    gl = Path(install_dir) / "spoke" / "managed" / "patterns" / "gate-log.jsonl"
    # also tolerate the v3 location
    if not gl.exists():
        gl = Path(install_dir).parent / "WAI-Spoke" / "patterns" / "gate-log.jsonl"
    if not gl.exists():
        return {"approval_rate": None, "open_halts": None}
    appr = halts = total = 0
    for line in gl.read_text(errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        d = e.get("disposition") or e.get("event")
        total += 1
        if d in ("approved", "certification"):
            appr += 1
        elif d in ("halted", "halt"):
            halts += 1
    return {"approval_rate": round(appr / total, 2) if total else None, "open_halts": halts}


def build_fleet_dashboard(registry_path, master_dir, now_iso=None):
    master_files = fleet_verify.load_manifest_files(Path(master_dir) / fleet_verify.MANIFEST_REL)
    rows = []
    summ = {"total": 0, "on_disk": 0, "integrity_pass": 0, "current": 0, "active": 0, "ready": 0}
    for s in _registry_spokes(registry_path):
        install = os.path.join(s["path"], "WAI-Harness")
        on_disk = os.path.isdir(s["path"])
        has_v4 = os.path.isdir(install)
        summ["total"] += 1
        if on_disk:
            summ["on_disk"] += 1
        if not has_v4:
            rows.append({"wheel_id": s["wheel_id"], "on_disk": on_disk, "has_v4": False,
                         "integrity": None, "currency": None, "activation": None,
                         "activation_ready": None, "pattern": {"approval_rate": None, "open_halts": None}})
            continue
        v = fleet_verify.classify_install(install, master_files)
        if v["integrity"] == "PASS":
            summ["integrity_pass"] += 1
        if v["currency"] == "CURRENT":
            summ["current"] += 1
        if v["activation"] == "ACTIVE":
            summ["active"] += 1
        if v["activation_ready"]:
            summ["ready"] += 1
        rows.append({"wheel_id": s["wheel_id"], "on_disk": on_disk, "has_v4": True,
                     "integrity": v["integrity"], "currency": v["currency"],
                     "activation": v["activation"], "activation_ready": v["activation_ready"],
                     "pattern": _pattern_monitor(install)})
    return {"generated_at": now_iso, "master": str(master_dir), "summary": summ,
            "rows": sorted(rows, key=lambda r: r["wheel_id"])}


def _render(dash):
    s = dash["summary"]
    print(f"FLEET DASHBOARD ({s['total']} registry spokes, non-archive)  master={dash['master']}")
    print(f"  on-disk {s['on_disk']}  |  integrity {s['integrity_pass']}  |  current {s['current']}  "
          f"|  ACTIVE {s['active']}  |  ready {s['ready']}")
    print(f"  {'spoke':<34} int cur act  appr halts")
    for r in dash["rows"]:
        intg = LIGHT[r['integrity'] == 'PASS'] if r['has_v4'] else "—"
        cur = LIGHT[r['currency'] == 'CURRENT'] if r['has_v4'] else "—"
        act = LIGHT[r['activation'] == 'ACTIVE'] if r['has_v4'] else "—"
        pm = r["pattern"]
        appr = "" if pm["approval_rate"] is None else f"{pm['approval_rate']:.0%}"
        halts = "" if pm["open_halts"] is None else str(pm["open_halts"])
        tag = "" if r["has_v4"] else ("  (no v4)" if r["on_disk"] else "  (MISSING on disk)")
        print(f"  {r['wheel_id']:<34}  {intg}   {cur}   {act}   {appr:>4} {halts:>5}{tag}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fleet Status christmas-tree dashboard (AC18)")
    ap.add_argument("--registry", default=DEFAULT_REGISTRY)
    ap.add_argument("--master", default=DEFAULT_MASTER)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--now-iso", default=None)
    a = ap.parse_args(argv)
    dash = build_fleet_dashboard(a.registry, a.master, now_iso=a.now_iso)
    if a.json:
        print(json.dumps(dash, indent=2))
    else:
        _render(dash)
    return 0


if __name__ == "__main__":
    sys.exit(main())
