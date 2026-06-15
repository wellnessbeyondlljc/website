#!/usr/bin/env python3
"""fleet_verify.py — repeatable fleet verification (integrity + parity + activation).

Generalizes the session-20260609-1605 ad-hoc fleet pass into one command
(task-fleet-recurrency-before-activation-v1 AC3). For every WAI-Harness install
under a root, reports three INDEPENDENT dimensions:

  integrity  — recompute MD5 of each managed file vs the install's OWN MANIFEST
               (manifest_build.verify). Catches corruption / unauthorized edits.
  parity     — compare the install's managed file-set+hashes vs the MASTER
               MANIFEST. missing = master file absent here; stale = present but
               hash differs; extra = here but not in master. CURRENT = none of
               {missing, stale}.
  activation — presence of the v4 activation marker (spoke/local/.activated).

A spoke is ACTIVATION-READY only when integrity ok AND parity CURRENT. The
'distributed before verification' risk is latent while a spoke is dormant; it
materializes at activation, so activation-readiness is reported here and ENFORCED
in harness_activate.py.

Pure helpers (load_manifest_files, compare_to_master, classify_install) are
path-injected and unit-tested in tests/test_fleet_verify.py.

CLI:
  fleet_verify.py [--root DIR] [--master DIR] [--json] [--report PATH]

Exit: 0 = all installs intact (integrity ok everywhere), 1 = any integrity
failure, 2 = error (e.g. master MANIFEST not found).
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Reuse the canonical MD5 + verify implementation — single source of truth.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import manifest_build  # noqa: E402

MANIFEST_REL = os.path.join("spoke", "managed", "MANIFEST.json")
MANAGED_REL = os.path.join("spoke", "managed")
ACTIVATED_REL = os.path.join("spoke", "local", ".activated")


def load_manifest_files(manifest_path) -> dict:
    """rel -> md5 map from a MANIFEST.json. Empty dict if absent/unreadable."""
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return {}
    try:
        data = json.load(open(manifest_path))
    except (ValueError, OSError):
        return {}
    return {rel: meta.get("md5") for rel, meta in data.get("files", {}).items()}


def compare_to_master(managed_dir, master_files: dict) -> dict:
    """Compare an install's managed/ tree against the master file->md5 map.

    missing = recorded in master but absent on disk here;
    stale   = present here but md5 differs from master;
    extra   = present here but not recorded in master.
    current = no missing and no stale (extras are informational, not a block).
    """
    managed_dir = Path(managed_dir)
    on_disk = {}
    if managed_dir.exists():
        for rel in master_files:
            full = managed_dir / rel
            on_disk[rel] = manifest_build._md5(full) if full.exists() else None
    missing, stale = [], []
    for rel, md5 in master_files.items():
        disk = on_disk.get(rel)
        if disk is None:
            missing.append(rel)
        elif disk != md5:
            stale.append(rel)
    # extras: any managed file on disk not in master (excl. bytecode/cache cruft)
    extra = []
    if managed_dir.exists():
        for dirpath, dirs, files in os.walk(managed_dir):
            dirs[:] = [d for d in dirs if d not in manifest_build._EXCLUDE_DIRS]
            for name in files:
                rel = os.path.relpath(os.path.join(dirpath, name), managed_dir)
                if rel == "MANIFEST.json" or manifest_build._excluded(rel):
                    continue
                if rel not in master_files:
                    extra.append(rel)
    return {
        "current": not (missing or stale),
        "missing": sorted(missing),
        "stale": sorted(stale),
        "extra": sorted(extra),
    }


def classify_install(install_dir, master_files: dict) -> dict:
    """Full verdict for one WAI-Harness install across all three dimensions."""
    install_dir = Path(install_dir)
    managed_dir = install_dir / MANAGED_REL
    manifest_path = install_dir / MANIFEST_REL

    # integrity: MD5 vs the install's OWN manifest
    if manifest_path.exists():
        integ = manifest_build.verify(str(managed_dir), str(manifest_path))
    else:
        integ = {"ok": False, "mismatches": [], "missing": [], "new": [],
                 "error": "no MANIFEST.json"}

    parity = compare_to_master(managed_dir, master_files)
    activated = (install_dir / ACTIVATED_REL).exists()

    ready = bool(integ.get("ok")) and parity["current"]
    return {
        "install": str(install_dir),
        "integrity": "PASS" if integ.get("ok") else "FAIL",
        "integrity_detail": integ,
        "currency": "CURRENT" if parity["current"] else "STALE",
        "parity": parity,
        "activation": "ACTIVE" if activated else "DORMANT",
        "activation_ready": ready,
    }


def find_installs(root, master_dir) -> list:
    """Every directory named WAI-Harness under root, excluding the master and
    anything under a trash_bin/ path. Sorted for stable output."""
    root = Path(root).resolve()
    master_dir = Path(master_dir).resolve()
    found = []
    for dirpath, dirs, _files in os.walk(root):
        # prune trash + node_modules + .git for speed
        dirs[:] = [d for d in dirs
                   if d not in (".git", "node_modules", "trash_bin")]
        if os.path.basename(dirpath) == "WAI-Harness":
            p = Path(dirpath).resolve()
            if p != master_dir:
                found.append(p)
            dirs[:] = []  # don't descend into an install
    return sorted(found)


def run(root, master_dir, now_iso=None) -> dict:
    master_dir = Path(master_dir).resolve()
    master_manifest = master_dir / MANIFEST_REL
    if not master_manifest.exists():
        raise FileNotFoundError(f"master MANIFEST not found: {master_manifest}")
    master_files = load_manifest_files(master_manifest)

    installs = find_installs(root, master_dir)
    results = [classify_install(p, master_files) for p in installs]

    n = len(results)
    integ_pass = sum(1 for r in results if r["integrity"] == "PASS")
    current = sum(1 for r in results if r["currency"] == "CURRENT")
    active = sum(1 for r in results if r["activation"] == "ACTIVE")
    ready = sum(1 for r in results if r["activation_ready"])
    return {
        "id": "fleet-verify",
        "run_at": now_iso,
        "root": str(Path(root).resolve()),
        "master": str(master_dir),
        "master_file_count": len(master_files),
        "summary": {
            "installs": n,
            "integrity_pass": integ_pass,
            "currency_current": current,
            "activation_active": active,
            "activation_ready": ready,
        },
        "installs": results,
    }


def _print_human(report: dict) -> None:
    s = report["summary"]
    print(f"Fleet verify — root {report['root']}")
    print(f"  master: {report['master']} ({report['master_file_count']} managed files)")
    print(f"  installs: {s['installs']}")
    print(f"  integrity:  PASS {s['integrity_pass']}/{s['installs']}")
    print(f"  currency:   CURRENT {s['currency_current']}/{s['installs']}")
    print(f"  activation: ACTIVE {s['activation_active']}/{s['installs']}")
    print(f"  activation-ready (integrity+current): {s['activation_ready']}/{s['installs']}")
    print()
    for r in report["installs"]:
        flags = []
        if r["currency"] == "STALE":
            p = r["parity"]
            flags.append(f"{len(p['missing'])} missing / {len(p['stale'])} stale")
        if r["integrity"] == "FAIL":
            flags.append("INTEGRITY FAIL")
        tail = f"  ({'; '.join(flags)})" if flags else ""
        print(f"  [{r['integrity']:4} | {r['currency']:7} | {r['activation']:7}] "
              f"{r['install']}{tail}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="repeatable fleet verification (integrity+parity+activation)")
    ap.add_argument("--root", default="/home/mario/projects",
                    help="root to scan for WAI-Harness installs")
    ap.add_argument("--master", default="/home/mario/projects/wheelwright/mywheel/WAI-Harness",
                    help="master wheel WAI-Harness dir")
    ap.add_argument("--json", action="store_true", help="emit JSON to stdout")
    ap.add_argument("--report", default=None, help="also write JSON report to this path")
    ap.add_argument("--now-iso", default=None, help="timestamp to stamp in the report")
    a = ap.parse_args(argv)

    try:
        report = run(a.root, a.master, now_iso=a.now_iso)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        json.dump(report, open(a.report, "w"), indent=2)

    if a.json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)

    s = report["summary"]
    return 0 if s["integrity_pass"] == s["installs"] else 1


if __name__ == "__main__":
    sys.exit(main())
