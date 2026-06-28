#!/usr/bin/env python3
"""scaffold_advisor_contract.py — emit a schema-conforming contract.json for an advisor.

P12 (Purposeful Objects): an advisor with NO contract.json is UNDEFINED and receives
no AP capacity (define-or-retire). This tool makes the "define" half mechanical and
fleet-repeatable: it infers as much of the canonical advisor contract as possible from
an advisor's own dir (charter.md / context_prompt.md / feeds.yaml / schedule.yaml) and
the advisor registry, and writes advisors/<id>/contract.json. Fields it cannot infer
(produces / downstream specifics) get sound defaults plus `needs_review: true` so the
owner refines them — but the advisor is DEFINED and fundable immediately.

Idempotent: skips an advisor that already has a contract.json unless --force.

CLI:
    # scaffold one advisor
    python3 scaffold_advisor_contract.py --advisors-dir WAI-Harness/spoke/advisors --id jordy
    # scaffold every KEEPER (has a prompt/charter or is the expediter) that lacks a contract
    python3 scaffold_advisor_contract.py --advisors-dir WAI-Harness/spoke/advisors --keepers
    # report keepers vs stubs without writing
    python3 scaffold_advisor_contract.py --advisors-dir WAI-Harness/spoke/advisors --list
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

# The expediter is a keeper by FUNCTION (queue engine), not by prompt.
SPECIAL_KEEPERS = {"expediter"}
# Dirs that are never advisors (engine/junk) — never scaffold these.
NON_ADVISORS = {"unknown", "autopilot", "registry.json", "schedule-index.json"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_meaningful_line(path: Path) -> str:
    if not path.exists():
        return ""
    for ln in path.read_text(errors="ignore").splitlines():
        s = ln.strip().lstrip("#").strip()
        if s and not s.startswith("---") and not s.lower().endswith("charter"):
            return s[:160]
    return ""


def _registry(advisors_dir: Path) -> dict:
    reg = advisors_dir / "registry.json"
    if not reg.exists():
        return {}
    try:
        data = json.loads(reg.read_text())
        if isinstance(data, list):
            return {r.get("advisor_id"): r for r in data if r.get("advisor_id")}
    except Exception:
        pass
    return {}


def is_keeper(adir: Path) -> bool:
    aid = adir.name
    if aid in NON_ADVISORS or not adir.is_dir():
        return False
    if aid in SPECIAL_KEEPERS:
        return True
    return (adir / "context_prompt.md").exists() or (adir / "charter.md").exists()


def infer_contract(adir: Path, reg: dict) -> dict:
    aid = adir.name
    r = reg.get(aid, {})
    inputs = [f.name for f in sorted(adir.iterdir())
              if f.is_file() and f.suffix in (".md", ".yaml", ".jsonl")
              and f.name not in ("contract.json",)]
    purpose = (r.get("title")
               or _first_meaningful_line(adir / "charter.md")
               or _first_meaningful_line(adir / "context_prompt.md")
               or f"TODO: one-line purpose for {aid}")
    kind = "crew" if (r.get("role_type") or "").startswith("crew") else "advisor"
    owner = "mywheel-master" if aid == "framework_development" else "spoke"

    if aid == "expediter":
        # The expediter is the work-availability/queue engine — its circuit is the
        # canonical 'expediter-work-availability' object, consumed by ozi + conductor.
        return _wrap(aid, {
            "advisor_id": aid,
            "purpose": "Maintains the spoke's work-availability + work/ready queues — the engine's own signal of whether there is fundable work.",
            "owner": "Basher",
            "kind": "advisor",
            "inputs": inputs or ["state.json", "deliver.py"],
            "produces": "work-availability.json + work-queue.json + ready-queue.json (the dispatch signal)",
            "consumed_by": "ozi | conductor",
            "downstream": "AP dispatch decision (fund / drain / skip) for this spoke",
            "productivity_signal": {
                "data_point": "work-availability advanced AND >=1 ready item became an in_progress/completed lug",
                "productive_if": "queues reflect real lugs that get actioned within the run window",
                "unproductive_if": "queues stay empty or only carry DEGRADED placeholder items across runs",
                "inactive_if": "no queue files / never delivered",
            },
            "cadence": "on-event",
            "retire_if": "never — core engine object (redefine, do not retire)",
        })

    return _wrap(aid, {
        "advisor_id": aid,
        "purpose": purpose,
        "owner": owner,
        "kind": kind,
        "inputs": inputs or ["context_prompt.md"],
        "produces": "findings -> advisor-scout-*.json lugs (recommendations for the expediter queue)",
        "consumed_by": "expediter | ozi",
        "downstream": "a routed lug that becomes an actioned/completed change",
        "productivity_signal": {
            "data_point": "runs.jsonl advanced AND >=1 finding became an actioned/completed lug",
            "productive_if": "downstream lug actioned within 3 runs",
            "unproductive_if": "ran/fired but produced no actioned output -> stop spending tokens",
            "inactive_if": "never ran (no runs.jsonl)",
        },
        "cadence": r.get("preferred_cadence") or "on-event",
        "retire_if": "active-unproductive across 3 consecutive cadences",
    })


def _wrap(aid: str, fields: dict) -> dict:
    fields["schema_version"] = "1.0"
    fields["_scaffolded"] = True
    fields["_scaffolded_at"] = now_iso()
    fields["_scaffolded_by"] = "scaffold_advisor_contract.py"
    # produces/downstream defaults are sound but generic — flag for owner refinement.
    fields["needs_review"] = aid not in SPECIAL_KEEPERS
    return fields


def scaffold(advisors_dir: Path, aid: str, force: bool, reg: dict) -> dict:
    adir = advisors_dir / aid
    dest = adir / "contract.json"
    if dest.exists() and not force:
        return {"id": aid, "action": "skip", "reason": "contract exists"}
    if not adir.is_dir():
        return {"id": aid, "action": "skip", "reason": "no advisor dir"}
    contract = infer_contract(adir, reg)
    dest.write_text(json.dumps(contract, indent=2) + "\n")
    return {"id": aid, "action": "wrote", "needs_review": contract.get("needs_review")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scaffold schema-conforming advisor contract.json")
    ap.add_argument("--advisors-dir", required=True)
    ap.add_argument("--id", help="scaffold a single advisor by id")
    ap.add_argument("--keepers", action="store_true", help="scaffold every keeper lacking a contract")
    ap.add_argument("--list", action="store_true", help="report keepers vs stubs (no write)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    advisors_dir = Path(args.advisors_dir)
    reg = _registry(advisors_dir)
    dirs = sorted(d for d in advisors_dir.iterdir() if d.is_dir())

    if args.list:
        keepers = [d.name for d in dirs if is_keeper(d)]
        stubs = [d.name for d in dirs if not is_keeper(d) and d.name not in NON_ADVISORS]
        contracted = [d.name for d in dirs if (d / "contract.json").exists()]
        out = {"keepers": keepers, "stubs_define_or_retire": stubs, "contracted": contracted}
        print(json.dumps(out, indent=2) if args.json else
              f"keepers ({len(keepers)}): {keepers}\n"
              f"stubs/define-or-retire ({len(stubs)}): {stubs}\n"
              f"already contracted ({len(contracted)}): {contracted}")
        return 0

    results = []
    if args.id:
        results.append(scaffold(advisors_dir, args.id, args.force, reg))
    elif args.keepers:
        for d in dirs:
            if is_keeper(d):
                results.append(scaffold(advisors_dir, d.name, args.force, reg))
    else:
        ap.error("specify --id, --keepers, or --list")

    wrote = [r for r in results if r["action"] == "wrote"]
    print(json.dumps(results, indent=2) if args.json else
          f"scaffolded {len(wrote)}/{len(results)}: "
          + ", ".join(f"{r['id']}({r['action']})" for r in results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
