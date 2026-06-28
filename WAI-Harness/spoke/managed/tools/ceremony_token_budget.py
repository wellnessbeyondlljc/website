#!/usr/bin/env python3
"""ceremony_token_budget.py — performance guard for the WAI ceremonies (P4 of
initiative-optimize-ceremonies-v1).

Ceremonies are loaded into the model's context every time they run, so their size
IS a per-run token cost. P0-P2 cut that cost (canonicalize, shared-lib, extract
~459L of inline Python to tools). This guard LOCKS IN those gains: each ceremony
has a line budget (a ceiling), and the cut/CI fails if a ceremony grows past it —
so the next edit can't silently re-bloat the ceremony back to the 1455L closeout.

Budgets are deliberate ceilings a bit above the post-optimization size; lowering a
budget after a real reduction is encouraged (ratchet down, never up without cause).

CLI:
  python3 ceremony_token_budget.py --commands DIR [--json]
Exit: 0 all within budget | 1 over budget | 2 error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# line-count ceilings (post-P0-P2). Ratchet DOWN as ceremonies shrink further.
BUDGETS = {
    "wai.md": 720,
    "wai-full.md": 500,
    "wai-full-slim.md": 60,
    "wai-reference.md": 360,
    "wai-reference-slim.md": 80,
    "wai-savepoint.md": 430,
    "wai-closeout.md": 1300,
    "wai-closeout-slim.md": 320,
    "wai-closeout-reference.md": 140,
}


def check(commands_dir: str) -> dict:
    over, ok, missing = [], [], []
    for name, budget in sorted(BUDGETS.items()):
        path = os.path.join(commands_dir, name)
        if not os.path.isfile(path):
            missing.append(name)
            continue
        with open(path) as fh:
            n = sum(1 for _ in fh)
        entry = {"file": name, "lines": n, "budget": budget, "headroom": budget - n}
        (over if n > budget else ok).append(entry)
    return {
        "ok": not over,
        "over": over, "within": ok, "missing": missing,
        "summary": f"{len(ok)} within budget, {len(over)} OVER, {len(missing)} missing",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Guard ceremony line budgets (token cost).")
    ap.add_argument("--commands", default="WAI-Harness/spoke/managed/.claude/commands")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rep = check(args.commands)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0 if rep["ok"] else 1
    if rep["ok"]:
        print(f"ceremony token budget: OK — {rep['summary']}")
        for e in sorted(rep["within"], key=lambda x: x["headroom"]):
            print(f"  {e['file']:28} {e['lines']:>5}/{e['budget']:<5} (headroom {e['headroom']})")
        return 0
    print(f"ceremony token budget: OVER — {rep['summary']}")
    for e in rep["over"]:
        print(f"  OVER {e['file']:24} {e['lines']}/{e['budget']} (+{-e['headroom']}) — trim or extract to a tool")
    return 1


if __name__ == "__main__":
    sys.exit(main())
