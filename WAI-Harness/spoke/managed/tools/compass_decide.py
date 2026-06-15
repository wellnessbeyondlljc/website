#!/usr/bin/env python3
"""
compass_decide.py — Record an approve / defer / reject decision against a queued item.

The Compass dashboard surfaces decisions sourced from high-impact signals,
needs-decision-tagged work-queue items, and Lathe shift proposals. This CLI
commits the user's response to the decision log so the gardener can act on
it during the next nightly pass.

Usage:
  compass_decide.py approve <id> [--reason TEXT] [--type TYPE] [--title TITLE] [--source-lug LUG_ID]
  compass_decide.py defer  <id> [--reason TEXT] [--until ISO-8601]
  compass_decide.py reject <id> [--reason TEXT]

Records to <hub>/WAI-Hub/advisors/compass/decisions.jsonl (one row per decision).
The hub path is resolved from --hub-path, $WAI_HUB_PATH, or defaults to ../hub
relative to this script.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent


def _resolve_hub_path(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    env = os.environ.get("WAI_HUB_PATH", "")
    if env:
        return Path(env).expanduser().resolve()
    fallback = _REPO_ROOT.parent / "hub"
    return fallback.resolve()


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def append_decision(hub_path: Path, decision: dict) -> Path:
    log_dir = hub_path / "WAI-Hub/advisors/compass"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "decisions.jsonl"
    with open(log_path, "a") as f:
        f.write(json.dumps(decision) + "\n")
    return log_path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["approve", "defer", "reject"])
    p.add_argument("decision_id")
    p.add_argument("--reason", default=None)
    p.add_argument("--type", default=None,
                   help="signal | lug | teaching | lathe — origin of the decision item")
    p.add_argument("--title", default=None)
    p.add_argument("--source-lug", default=None,
                   help="Originating lug id, when the decision was raised by a work-queue item.")
    p.add_argument("--until", default=None,
                   help="For defer: ISO-8601 timestamp to revisit.")
    p.add_argument("--hub-path", default=None)
    args = p.parse_args()

    if args.action == "defer" and args.until:
        try:
            datetime.datetime.fromisoformat(args.until.replace("Z", "+00:00"))
        except ValueError:
            print(f"[compass_decide] --until must be ISO-8601, got {args.until!r}",
                  file=sys.stderr)
            return 1

    hub_path = _resolve_hub_path(args.hub_path)

    decision = {
        "id": args.decision_id,
        "ts": _now_iso(),
        "action": args.action,
        "reason": args.reason,
        "type": args.type,
        "title": args.title,
        "source_lug": args.source_lug,
        "outcome_ts": None,
    }
    if args.action == "defer" and args.until:
        decision["defer_until"] = args.until

    decision = {k: v for k, v in decision.items() if v is not None}

    log_path = append_decision(hub_path, decision)
    print(f"recorded: {decision['action']} {decision['id']} -> {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
