#!/usr/bin/env python3
"""harness_status.py - basic interrogation of a spoke's v3/v4 harness state.

The coexistence safety net needs a way to ASK "what harness(es) does this spoke
have, which one is active, and is the v4 managed tree intact?" - in any mode,
including while v3 legacy files are still present. This is that interrogation. It
mirrors .claude/hooks/harness_mode.sh (same detection) and adds a managed-integrity
check when v4 is present, so a missed/corrupt file is visible (and patchable via the
v3 overlap) rather than silent.

Pure core: detect(spoke_root, override) -> dict. CLI prints it (human or --json).
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def detect(spoke_root=".", override=None):
    root = Path(spoke_root)
    v3 = (root / "WAI-Spoke").is_dir()
    v4 = (root / "WAI-Harness").is_dir()
    if v3 and v4:
        mode = "coexist"
    elif v4:
        mode = "v4-only"
    elif v3:
        mode = "v3-only"
    else:
        mode = "none"

    override = override or os.environ.get("WAI_HARNESS_MODE")
    if override == "v4" and v4:
        active = "v4"
    elif override == "v3" and v3:
        active = "v3"
    elif v4:
        active = "v4"
    elif v3:
        active = "v3"
    else:
        active = "none"

    info = {
        "spoke_root": str(root),
        "v3_present": v3, "v4_present": v4,
        "mode": mode, "active": active,
        "active_root": (str(root / ("WAI-Harness" if active == "v4" else "WAI-Spoke"))
                        if active != "none" else None),
        "v4_managed_verify": None,
    }

    # when v4 is present, interrogate its managed integrity (a missed/corrupt file
    # is surfaced here so the v3 overlap can cover it until patched)
    if v4:
        managed = root / "WAI-Harness" / "spoke" / "managed"
        try:
            import harness_upgrade as hu
            mpath = managed / hu.MANIFEST_NAME
            if mpath.exists():
                r = hu.verify(managed, hu.load_manifest(managed))
                info["v4_managed_verify"] = {
                    "ok": r["ok"], "mismatches": len(r["mismatches"]),
                    "missing": len(r["missing"])}
            else:
                info["v4_managed_verify"] = {"ok": None, "note": "no MANIFEST.json"}
        except Exception as e:
            info["v4_managed_verify"] = {"ok": None, "note": f"verify unavailable: {e}"}

        # master<->spoke version drift (impl-harness-couple-version-cut-and-adoption-gate-v1):
        # make 'spoke behind/ahead of master' observable instead of discovered by a hand-run
        # pull. Reports both harness_versions + an in_sync verdict; silent-skip if unresolved.
        try:
            import harness_upgrade as hu  # noqa: F811
            spoke_ver = hu.load_manifest(managed).get("harness_version") if mpath.exists() else None
            master_managed = hu._resolve_managed(hu.resolve_master(str(root)), "spoke")
            mm = Path(master_managed) / hu.MANIFEST_NAME
            master_ver = hu.load_manifest(master_managed).get("harness_version") if mm.exists() else None
            info["version_drift"] = {
                "spoke": spoke_ver, "master": master_ver,
                "in_sync": (spoke_ver == master_ver) if (spoke_ver and master_ver) else None,
            }
        except Exception as e:
            info["version_drift"] = {"spoke": None, "master": None, "in_sync": None, "note": str(e)}
    return info


def render(info):
    lines = [
        "WAI HARNESS STATUS",
        f"  spoke:   {info['spoke_root']}",
        f"  present: v3={info['v3_present']}  v4={info['v4_present']}  -> mode={info['mode']}",
        f"  active:  {info['active']}  ({info['active_root'] or 'n/a'})",
    ]
    mv = info["v4_managed_verify"]
    if mv is not None:
        if mv.get("ok") is True:
            lines.append("  v4 managed: VERIFIED (intact)")
        elif mv.get("ok") is False:
            lines.append(f"  v4 managed: DRIFT — {mv['mismatches']} mismatch / {mv['missing']} missing "
                         "(v3 overlap covers until patched)")
        else:
            lines.append(f"  v4 managed: {mv.get('note')}")
    vd = info.get("version_drift")
    if vd and (vd.get("spoke") or vd.get("master")):
        if vd.get("in_sync") is True:
            lines.append(f"  version:    {vd['spoke']} (in sync with master)")
        elif vd.get("in_sync") is False:
            lines.append(f"  version:    spoke {vd['spoke']} != master {vd['master']} — DRIFT (pull to sync)")
        else:
            lines.append(f"  version:    spoke {vd.get('spoke')} / master {vd.get('master')} (drift unknown)")
    if info["mode"] == "coexist":
        lines.append("  coexistence: v3 + v4 both available; set WAI_HARNESS_MODE=v3|v4 to pin the active one")
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description="Interrogate a spoke's v3/v4 harness state.")
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--mode", choices=["v3", "v4"], default=None, help="override active selection")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    info = detect(args.spoke_root, override=args.mode)
    print(json.dumps(info, indent=2) if args.json else render(info))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
