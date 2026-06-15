#!/usr/bin/env python3
"""Single-channel lint: resume state must NOT live on a lug.

Closes gap (B) of impl-savepoint-loss-safety-net-v1. The resume path (/wai, the
savepoint menu) reads the savepoints dir ONLY. A session that stashes its resume
narrative as a field ON a lug (savepoint_note, resume_note, work_done,
first_actions, pending_handoffs) creates state that LOOKS saved but is invisible
to the next session — exactly the loss observed in session-20260609-1605, where
the user had to hand-paste a prior session's resume state.

Rule (doctrine, spec-savepoint-resume-contract-v1): lugs carry WORK state; resume
/handoff state lives ONLY in <working-base>/savepoints/ (or closeout
incomplete_work). This lint rejects a lug carrying any resume-state field and
points the author to write a real savepoint instead.

CLI:
    python3 tools/check_lug_no_resume_state.py <lug.json> [<lug.json> ...]
    python3 tools/check_lug_no_resume_state.py --all [--root DIR]
    exit 0 = clean; exit 1 = at least one lug carries a banned resume-state field.
"""
import argparse
import glob
import json
import os
import sys

# Fields that belong to a SAVEPOINT, never to a lug. (work_done/first_actions/
# pending_handoffs are the savepoint resume-contract fields; *_note variants are
# the ad-hoc side channel observed in the wild.)
BANNED_FIELDS = (
    "savepoint_note",
    "resume_note",
    "resume_contract",
    "work_done",
    "first_actions",
    "pending_handoffs",
)


def check_lug(path):
    """Return a list of banned field names present at the top level of the lug."""
    try:
        d = json.load(open(path))
    except Exception as e:
        return ["<unreadable: %s>" % e]
    if not isinstance(d, dict):
        return []
    return [f for f in BANNED_FIELDS if f in d]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lugs", nargs="*", help="lug json paths to check")
    ap.add_argument("--all", action="store_true", help="check every lug under the tree")
    ap.add_argument("--root", default=".", help="spoke root (default .)")
    a = ap.parse_args()

    paths = list(a.lugs)
    if a.all:
        for base in ("WAI-Spoke", os.path.join("WAI-Harness", "spoke", "local")):
            paths += glob.glob(os.path.join(a.root, base, "lugs", "**", "*.json"), recursive=True)
    paths = sorted(set(paths))
    if not paths:
        print("no lugs to check")
        return 0

    failed = False
    for p in paths:
        banned = check_lug(p)
        if banned:
            failed = True
            print("REJECT %s" % p)
            print("  carries resume-state field(s): %s" % ", ".join(banned))
            print("  -> resume state lives ONLY in <working-base>/savepoints/. "
                  "Write a savepoint (see wai-savepoint); a lug carries WORK state, not RESUME state.")
    if not failed:
        print("clean: %d lug(s) carry no resume-state fields" % len(paths))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
