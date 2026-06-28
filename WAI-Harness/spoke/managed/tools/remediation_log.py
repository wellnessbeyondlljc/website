#!/usr/bin/env python3
"""remediation_log.py — audit trail for self-mitigating cross-project runs.

When an agent/orchestrator touches a project OTHER than the one it started in
(distributing a fix, soft-deleting garbage, reconciling state), it MUST record what
it did and why — in the touched project AND in the fleet master ledger. This makes
cross-project authority safe and reversible: every change is traceable to a session,
a reason, and a file list.

Writes two places (both append-only JSONL):
  - <project>/WAI-Harness/spoke/local/runtime/remediation-log.jsonl   (the touched project)
  - <master>/WAI-Harness/spoke/local/runtime/fleet-remediation-log.jsonl (mywheel, fleet view)

Usage:
  remediation_log.py --project /home/mario/projects/minder \
      --action soft-delete --reason "phantom WAI-Spoke advisor tree (v3-fallback bug)" \
      --files WAI-Harness/spoke/local/WAI-Spoke --session session-... --by claude-opus

API: record(project, action, reason, files=(), session=None, by=None, master=None) -> dict
"""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MASTER = "/home/mario/projects/wheelwright/mywheel"


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _append(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")


def record(project, action, reason, files=(), session=None, by=None, master=None):
    """Append a remediation record to the touched project + the fleet master ledger."""
    project = Path(project).resolve()
    master = Path(master or DEFAULT_MASTER).resolve()
    rec = {
        "ts": _utcnow(),
        "session": session or os.environ.get("WAI_SESSION_ID"),
        "by": by or os.environ.get("WAI_AGENT") or "agent",
        "action": action,
        "reason": reason,
        "files": list(files),
        "project": str(project),
    }
    _append(project / "WAI-Harness" / "spoke" / "local" / "runtime" / "remediation-log.jsonl", rec)
    if project != master:
        _append(master / "WAI-Harness" / "spoke" / "local" / "runtime" / "fleet-remediation-log.jsonl", rec)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description="Record a self-mitigating cross-project touch")
    ap.add_argument("--project", required=True)
    ap.add_argument("--action", required=True, help="verb: soft-delete | distribute | reconcile | edit | ...")
    ap.add_argument("--reason", required=True)
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--session", default=None)
    ap.add_argument("--by", default=None)
    ap.add_argument("--master", default=None)
    a = ap.parse_args(argv)
    rec = record(a.project, a.action, a.reason, a.files, a.session, a.by, a.master)
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
