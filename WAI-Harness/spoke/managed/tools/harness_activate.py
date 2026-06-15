#!/usr/bin/env python3
"""harness_activate.py — on-load v4 activation + migration trigger (DORMANT by default).

After a non-destructive install a spoke holds both `WAI-Spoke/` (v3) and `WAI-Harness/`
(v4) but keeps running v3 — nothing auto-switches. This is the piece that lets a spoke
NOTICE it has been upgraded and, ONLY when explicitly opted in, migrate its v3 working
state into the v4 `local/` tree and mark itself activated. It is the mechanism a root
.claude session-start calls; the actual hook wiring is Basher's (.claude canon).

Safety design (every gate is deliberate):
  - DORMANT by default: nothing migrates unless an explicit `WAI-Harness/ACTIVATE`
    marker exists (the human cutover opt-in). check_on_load() with no marker just
    reports "upgraded, dormant" — that is the "agent notices" behavior.
  - PARITY GATE: activation REFUSES when the spoke's managed/ is stale vs the master
    MANIFEST (missing/changed files). Activating a stale snapshot would run a
    pre-hardening, partially-built v4 — the "distributed before verification" risk
    materializes exactly at activation, so it is blocked here. --force overrides
    (records forced). (task-fleet-recurrency-before-activation-v1 AC1)
  - DRY-RUN first: migrate() previews by default and writes nothing.
  - IDEMPOTENT: a `.activated` marker stops re-migration on every subsequent load.
  - NON-DESTRUCTIVE: v3 state is COPIED into v4 local/, never moved/deleted — v3
    stays as the instant fallback (WAI_HARNESS_MODE=v3).
  - NO-ORPHAN visibility: v3 categories not in the home-map are reported (they
    remain in v3, accessible), never silently dropped.

Pure core: status / find_orphans / parity_blockers / migrate / activate.
check_on_load is the session-start entry point. CLI wraps with IO.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

# Reuse the canonical parity comparison — single source of truth for "stale vs master".
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import fleet_verify  # noqa: E402

ACTIVATE_MARKER = "ACTIVATE"                       # under WAI-Harness/ (human opt-in)
ACTIVATED_MARKER = "spoke/local/.activated"        # under WAI-Harness/ (idempotency)
MANAGED_REL = "spoke/managed"                       # under WAI-Harness/
DEFAULT_MASTER = "/home/mario/projects/wheelwright/mywheel/WAI-Harness"

# per-spoke migration home-map: v3 WAI-Spoke/<key> -> v4 WAI-Harness/<value>.
# Every v3 working-state category that should carry into v4 is listed here; what is
# NOT listed stays in v3 (reported as not-migrated, never lost — v3 is untouched).
HOME_MAP = {
    "WAI-State.json": "spoke/local/WAI-State.json",
    "sessions":       "spoke/local/sessions",
    "lugs":           "spoke/local/lugs",
    "savepoints":     "spoke/local/savepoints",
    "initiatives":    "spoke/local/initiatives",
    "signals":        "spoke/local/signals",
    "bolts":          "spoke/local/bolts",
    "teachings":      "spoke/local/teachings",
    "kpi":            "spoke/local/kpi",
    "advisors":       "spoke/advisors",
}


def status(spoke_root):
    """not_upgraded | upgraded_dormant | activation_requested | activated."""
    root = Path(spoke_root)
    if not (root / "WAI-Harness").is_dir():
        return "not_upgraded"
    if (root / "WAI-Harness" / ACTIVATED_MARKER).exists():
        return "activated"
    if (root / "WAI-Harness" / ACTIVATE_MARKER).exists():
        return "activation_requested"
    return "upgraded_dormant"


def find_orphans(spoke_root):
    """v3 WAI-Spoke top-level entries not claimed by the home-map (stay in v3)."""
    ws = Path(spoke_root) / "WAI-Spoke"
    if not ws.is_dir():
        return []
    claimed = set(HOME_MAP)
    return sorted(p.name for p in ws.iterdir() if p.name not in claimed)


def parity_blockers(spoke_root, master_dir):
    """Reasons this spoke must NOT activate: its WAI-Harness/spoke/managed is stale
    vs the master MANIFEST. Empty list = at parity, clear to activate. A missing
    master MANIFEST is itself a blocker (cannot prove currency)."""
    master_manifest = Path(master_dir) / fleet_verify.MANIFEST_REL
    if not master_manifest.exists():
        return [f"master MANIFEST not found: {master_manifest}"]
    master_files = fleet_verify.load_manifest_files(master_manifest)
    managed_dir = Path(spoke_root) / "WAI-Harness" / MANAGED_REL
    parity = fleet_verify.compare_to_master(managed_dir, master_files)
    if parity["current"]:
        return []
    return [f"stale vs master ({len(parity['missing'])} missing, "
            f"{len(parity['stale'])} changed) — bring current before activation"]


def migrate(spoke_root, dry_run=True):
    """Seed v4 local/ from v3 WAI-Spoke per the home-map. COPIES (never moves).
    Returns a report; dry_run writes nothing."""
    root = Path(spoke_root)
    ws, wh = root / "WAI-Spoke", root / "WAI-Harness"
    planned, skipped = [], []
    for src_name, dst_rel in HOME_MAP.items():
        src = ws / src_name
        if not src.exists():
            skipped.append({"src": src_name, "reason": "absent in v3"})
            continue
        dst = wh / dst_rel
        planned.append({"src": f"WAI-Spoke/{src_name}", "dst": f"WAI-Harness/{dst_rel}",
                        "kind": "dir" if src.is_dir() else "file"})
        if not dry_run:
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for item in src.rglob("*"):
                    if item.is_file():
                        target = dst / item.relative_to(src)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, target)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    return {"dry_run": dry_run, "migrated": planned, "skipped": skipped,
            "orphans_left_in_v3": find_orphans(spoke_root)}


def activate(spoke_root, dry_run=True, master_dir=None, force=False):
    """If activation is requested and not yet done: GATE on master parity, then
    migrate, then write the .activated marker. Idempotent + dormant; returns a
    report. The parity gate runs only on a real apply (dry_run=False) when a
    master_dir is supplied; --force overrides but records forced=True."""
    st = status(spoke_root)
    report = {"status_before": st, "dry_run": dry_run}
    if st in ("not_upgraded", "upgraded_dormant"):
        report["action"] = "none"
        report["note"] = ("dormant — create WAI-Harness/ACTIVATE to opt in"
                          if st == "upgraded_dormant" else "no WAI-Harness present")
        return report
    if st == "activated":
        report["action"] = "none"
        report["note"] = "already activated (idempotent no-op)"
        return report

    # activation_requested — enforce the parity gate before any real migration
    blockers = parity_blockers(spoke_root, master_dir) if (master_dir and not dry_run) else []
    if blockers and not force:
        report["action"] = "blocked"
        report["blocked"] = True
        report["blockers"] = blockers
        report["note"] = ("activation refused — managed/ not at master parity. "
                          "Run harness_upgrade to bring current, then retry (--force overrides).")
        return report

    report["migration"] = migrate(spoke_root, dry_run=dry_run)
    report["action"] = "migrate" + ("" if dry_run else "+mark-activated")
    report["forced"] = bool(blockers and force)
    if not dry_run:
        marker = Path(spoke_root) / "WAI-Harness" / ACTIVATED_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({
            "activated": True,
            "parity": "current" if not blockers else "FORCED-STALE",
            "forced": bool(blockers and force),
        }) + "\n")
        report["status_after"] = status(spoke_root)
    return report


def check_on_load(spoke_root, master_dir=None):
    """Session-start entry point. Reports the upgrade state (the 'agent notices'
    behavior) and, ONLY when activation is explicitly requested, performs the real
    (parity-gated) migration. Dormant/activated states are a no-op."""
    st = status(spoke_root)
    msg = {
        "not_upgraded": "v3 only — no WAI-Harness present.",
        "upgraded_dormant": "v4 AVAILABLE (dormant). Running v3. Create WAI-Harness/ACTIVATE to migrate.",
        "activation_requested": "v4 activation requested — checking parity, then migrating v3 state into v4 local/ …",
        "activated": "v4 ACTIVE (migration done).",
    }[st]
    out = {"status": st, "message": msg}
    if st == "activation_requested":
        # Pass master_dir through unchanged. The parity gate engages only when a
        # master_dir is supplied (see activate()); the production CLI (main) always
        # passes --master (default DEFAULT_MASTER), so the fleet gate stays enforced.
        # A None here (in-process callers / test fixtures) runs migration WITHOUT the
        # gate, so migration behavior is testable in isolation from a real master.
        out["result"] = activate(spoke_root, dry_run=False, master_dir=master_dir)
    return out


def main(argv):
    ap = argparse.ArgumentParser(description="v4 on-load activation + migration trigger (dormant by default).")
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--master", default=DEFAULT_MASTER, help="master wheel WAI-Harness dir (parity gate)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("check")                                   # the on-load entry point
    m = sub.add_parser("migrate"); m.add_argument("--apply", action="store_true")
    a = sub.add_parser("activate")
    a.add_argument("--apply", action="store_true")
    a.add_argument("--force", action="store_true", help="override the parity gate (records forced)")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        print(json.dumps({"status": status(args.spoke_root),
                          "orphans_left_in_v3": find_orphans(args.spoke_root)}, indent=2))
    elif args.cmd == "check":
        print(json.dumps(check_on_load(args.spoke_root, master_dir=args.master), indent=2))
    elif args.cmd == "migrate":
        print(json.dumps(migrate(args.spoke_root, dry_run=not args.apply), indent=2))
    elif args.cmd == "activate":
        res = activate(args.spoke_root, dry_run=not args.apply,
                       master_dir=args.master, force=args.force)
        print(json.dumps(res, indent=2))
        return 1 if res.get("blocked") else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
