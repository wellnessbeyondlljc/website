#!/usr/bin/env python3
"""
wayfinder_cycle_close.py — Emit a Wayfinder cycle-completion review lug.

Implements SOP-8 of templates/commands/wai-wayfinder.md. Called by Wayfinder
after a scout expedition completes; writes a task lug into
WAI-Spoke/lugs/bytype/task/open/ that invites Ozi to coordinate advisor review
before the next expedition.

Usage:
  python3 tools/wayfinder_cycle_close.py \\
      --scouts-run 5 --passed 3 --failed 2 \\
      --lugs-filed 2 --budget-pct 72 \\
      --session-id session-20260522-1702 \\
      [--scouts-authored 1] [--notes "Focus: Archie continuity"]
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)

# Make sibling tools/ modules importable when invoked directly
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from _schema_validate import validate_dict as _validate_against_schema  # noqa: E402,F401

SCHEMA_PATH = os.path.join(
    _REPO_ROOT, "WAI-Spoke/reference/wayfinder-cycle-close.schema.json"
)
LUG_OUT_DIR = os.path.join(_REPO_ROOT, "WAI-Spoke/lugs/bytype/task/open")


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def build_lug(args: argparse.Namespace) -> dict:
    now = _utc_now()
    lug_id = f"task-wayfinder-cycle-{now.strftime('%Y%m%d%H%M%S')}-v1"

    summary = {
        "scouts_run": args.scouts_run,
        "passed": args.passed,
        "failed": args.failed,
        "lugs_filed": args.lugs_filed,
        "budget_consumed_pct": args.budget_pct,
    }
    if args.scouts_authored:
        summary["scouts_authored"] = args.scouts_authored

    title = (
        f"Wayfinder cycle complete — "
        f"{args.passed}/{args.scouts_run} scouts passed, "
        f"{args.lugs_filed} lug(s) filed"
    )

    request = (
        "Invite all advisors to review their scout libraries, "
        "update schedule.yaml, and author new custom scouts before next expedition."
    )

    lug = {
        "id": lug_id,
        "type": "task",
        "status": "open",
        "title": title,
        "assigned_to": "ozi",
        "expedition_summary": summary,
        "request": request,
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "created_by": "wayfinder",
        "parent_session_id": args.session_id,
        "scope": "spoke_local",
    }
    if args.notes:
        lug["notes"] = args.notes

    return lug


def write_lug(lug: dict) -> str:
    os.makedirs(LUG_OUT_DIR, exist_ok=True)
    out_path = os.path.join(LUG_OUT_DIR, f"{lug['id']}.json")
    with open(out_path, "w") as f:
        json.dump(lug, f, indent=2)
        f.write("\n")
    return out_path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scouts-run",   type=int, required=True)
    p.add_argument("--passed",       type=int, required=True)
    p.add_argument("--failed",       type=int, required=True)
    p.add_argument("--lugs-filed",   type=int, required=True)
    p.add_argument("--budget-pct",   type=int, required=True)
    p.add_argument("--session-id",   type=str, required=True)
    p.add_argument("--scouts-authored", type=int, default=0)
    p.add_argument("--notes",        type=str, default=None)
    args = p.parse_args()

    if not os.path.isfile(SCHEMA_PATH):
        print(f"[wayfinder_cycle_close] schema missing: {SCHEMA_PATH}", file=sys.stderr)
        return 1
    schema = json.load(open(SCHEMA_PATH))

    lug = build_lug(args)
    errors = _validate_against_schema(lug, schema)
    if errors:
        print("[wayfinder_cycle_close] schema validation failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    out_path = write_lug(lug)
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
