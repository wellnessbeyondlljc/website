#!/usr/bin/env python3
"""audit_cg_registration.py — CapabilitiesGraph command-registration completeness (AC16).

AC16's first half (mandated/recommended/awareness tiers, hub-superset, spoke-inherits) is
built (resolve_capabilities_graph.py + materialize_cg.py + the hub CG seed). This closes the
SECOND half: "every spoke command is registered in the CG." It discovers every runnable
command/skill on disk and cross-checks that each is registered as a CG entry; anything
unregistered is surfaced as a `decision-undocumented` gap (verification_spine.GAP_TYPES),
never silently absent.

Pure core (discover_commands / registered_basenames / audit_registration) is path-injected
and unit-tested. CLI resolves the live CG via resolve_capabilities_graph.resolve_from_tree.

Exit: 0 = every discovered command registered (or explicitly declined), 1 = unregistered
commands exist, 2 = error.
"""
import argparse
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

GAP_TYPE = "decision-undocumented"   # an on-disk command absent from the CG is an undocumented decision
DEFAULT_COMMAND_DIRS = ("templates/commands", "skills")


def discover_commands(spoke_root, command_dirs=DEFAULT_COMMAND_DIRS):
    """Every *.md command/skill on disk under the given dirs, as basenames mapped to
    their relpath-from-spoke_root. Basename is the registration key (templates/commands/
    is canonical; .claude/commands/ is its distributed copy — same basename)."""
    spoke_root = Path(spoke_root)
    found = {}
    for d in command_dirs:
        base = spoke_root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            rel = os.path.relpath(p, spoke_root)
            found[p.name] = rel
    return found


def registered_basenames(cg_entries):
    """Basenames of every file referenced by a CG entry's file_paths (the set of
    commands/skills the CG knows about)."""
    out = set()
    for e in cg_entries:
        for fp in e.get("file_paths", []) or []:
            out.add(os.path.basename(fp))
    return out


def audit_registration(discovered, cg_entries, declined=None):
    """discovered: {basename -> relpath}. Returns a report. `declined` is an optional set
    of basenames explicitly NOT to register (recorded, not counted as gaps)."""
    declined = set(declined or [])
    registered = registered_basenames(cg_entries)
    unreg, reg = [], []
    for name, rel in sorted(discovered.items()):
        if name in registered or name in declined:
            reg.append(rel)
        else:
            unreg.append(rel)
    total = len(discovered)
    gaps = [{"gap_type": GAP_TYPE, "command": rel,
             "detail": "on-disk command not registered in the CapabilitiesGraph"}
            for rel in unreg]
    return {
        "total_commands": total,
        "registered": len(reg),
        "unregistered": unreg,
        "declined": sorted(declined),
        "coverage_pct": round(100.0 * len(reg) / total, 1) if total else 100.0,
        "gaps": gaps,
        "ok": not unreg,
    }


def _resolve_cg_entries(mywheel_path, cg_file):
    if cg_file:
        return json.loads(Path(cg_file).read_text()).get("entries", [])
    try:
        import resolve_capabilities_graph as rcg
        return rcg.resolve_from_tree(mywheel_path).get("entries", [])
    except Exception as e:  # noqa: BLE001
        print(f"ERROR resolving CG: {e}", file=sys.stderr)
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="audit CG command-registration completeness (AC16)")
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--mywheel", default="/home/mario/projects/wheelwright/mywheel",
                    help="mywheel ROOT (the dir CONTAINING WAI-Harness; resolve_from_tree joins WAI-Harness/...)")
    ap.add_argument("--cg-file", default=None, help="explicit resolved CG json (else resolve from --mywheel)")
    ap.add_argument("--command-dirs", nargs="*", default=list(DEFAULT_COMMAND_DIRS))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    entries = _resolve_cg_entries(a.mywheel, a.cg_file)
    if entries is None:
        return 2
    discovered = discover_commands(a.spoke_root, a.command_dirs)
    report = audit_registration(discovered, entries)
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"CG registration: {report['registered']}/{report['total_commands']} "
              f"({report['coverage_pct']}%) registered; {len(report['unregistered'])} unregistered")
        for rel in report["unregistered"][:40]:
            print(f"  [gap:{GAP_TYPE}] {rel}")
        if len(report["unregistered"]) > 40:
            print(f"  ... +{len(report['unregistered']) - 40} more")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
