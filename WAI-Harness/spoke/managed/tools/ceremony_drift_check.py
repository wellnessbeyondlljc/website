#!/usr/bin/env python3
"""ceremony_drift_check.py — cut-gate guard: the ceremony/command set must have ONE
canonical source and no drift.

Canonical source: WAI-Harness/spoke/managed/.claude/commands/.
Two invariants checked:
  1. ACTIVE drift — every managed command is present + byte-identical in the active
     dir <root>/.claude/commands/ (the operator must invoke the canonical, never a
     stale copy). Run deploy_commands.py to fix.
  2. TEMPLATE drift — the onboarding template copy
     WAI-Harness/spoke/managed/templates/commands/ must be byte-identical to the
     canonical (it is a generated mirror, not a hand-maintained fork). Regenerate
     from the canonical to fix.

Active-only LOCAL commands (present in the active dir but not in managed) are allowed
and ignored. Retired commands (deploy_commands.RETIRED) must NOT be present anywhere.

CLI:
    python3 ceremony_drift_check.py --root DIR [--json]
Exit: 0 no drift | 1 drift found | 2 error.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import sys
from pathlib import Path

MANAGED_REL = "WAI-Harness/spoke/managed/.claude/commands"
ACTIVE_REL = ".claude/commands"
TEMPLATE_REL = "WAI-Harness/spoke/managed/templates/commands"

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from deploy_commands import RETIRED
except Exception:
    RETIRED = ()


def check(spoke_root: str) -> dict:
    root = Path(spoke_root).resolve()
    managed = root / MANAGED_REL
    active = root / ACTIVE_REL
    template = root / TEMPLATE_REL
    if not managed.is_dir():
        return {"ok": False, "error": f"managed commands dir not found: {managed}"}

    managed_files = sorted(p for p in managed.glob("*.md") if p.is_file())
    active_drift, template_drift, retired_present = [], [], []

    for src in managed_files:
        a = active / src.name
        if not a.exists():
            active_drift.append({"file": src.name, "why": "missing in active dir"})
        elif not filecmp.cmp(src, a, shallow=False):
            active_drift.append({"file": src.name, "why": "active copy differs from canonical"})
        if template.is_dir():
            t = template / src.name
            if not t.exists():
                template_drift.append({"file": src.name, "why": "missing in template dir"})
            elif not filecmp.cmp(src, t, shallow=False):
                template_drift.append({"file": src.name, "why": "template copy differs from canonical"})

    for name in RETIRED:
        for label, d in (("active", active), ("template", template), ("managed", managed)):
            if (d / name).exists():
                retired_present.append({"file": name, "where": label})

    drift = bool(active_drift or template_drift or retired_present)
    return {
        "ok": not drift,
        "active_drift": active_drift,
        "template_drift": template_drift,
        "retired_present": retired_present,
        "summary": (f"{len(active_drift)} active, {len(template_drift)} template, "
                    f"{len(retired_present)} retired-present"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Guard against ceremony/command drift.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rep = check(args.root)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0 if rep.get("ok") else (2 if "error" in rep else 1)
    if "error" in rep:
        print(f"ceremony_drift_check: ERROR — {rep['error']}", file=sys.stderr)
        return 2
    if rep["ok"]:
        print("ceremony drift: CLEAN — active + template mirror the canonical command set.")
        return 0
    print(f"ceremony drift: FOUND — {rep['summary']}")
    for d in rep["active_drift"]:
        print(f"  [active]   {d['file']}: {d['why']}  (run deploy_commands.py)")
    for d in rep["template_drift"]:
        print(f"  [template] {d['file']}: {d['why']}  (regenerate template from canonical)")
    for d in rep["retired_present"]:
        print(f"  [retired]  {d['file']} still present in {d['where']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
