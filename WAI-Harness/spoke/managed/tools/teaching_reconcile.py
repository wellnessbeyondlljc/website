#!/usr/bin/env python3
"""Teaching reconciliation: classify a spoke teaching index into base + patches.

Implements the grooming logic behind the <=10 patch cap. Given a teaching
`index.json`, classify every entry as:

  KEEP       genuinely unabsorbed behavior  -> promote to patches/ (counts to <=10)
  ABSORBED   the base already implements it  -> archive + absorbed_in_base_version
  STALE      raw event signal / no-title / project-specific -> archive + reason
  DUPLICATE  older where a newer version exists -> archive, keep newer

Automatable verdicts (STALE via id/title patterns, DUPLICATE via supersedes and
version suffixes) are decided here. ABSORBED requires confirming behavior against
harness files; entries flagged `absorbed_hint` (e.g. from the audit lug's
known-categories list) are proposed ABSORBED for human confirmation, everything
else defaults to KEEP-or-review.

Default mode is dry-run: it prints the plan and the cap check. `--apply`
executes file moves against the given dirs (used for the hub run, deferred).

CLI:
  python3 tools/teaching_reconcile.py plan --index <index.json> \
      [--absorbed-hints <ids.json>] [--cap 10]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Raw-event-signal / unpublishable patterns -> STALE.
STALE_PATTERNS = [
    re.compile(r"^signal-\d{8}"),          # dated event signals
    re.compile(r"-from-\w+$"),              # signal-...-from-minder
    re.compile(r"session\d+", re.I),        # ancient session refs
]
# Trailing -v{n} version suffix for duplicate detection.
VER_RE = re.compile(r"^(?P<stem>.+)-v(?P<n>\d+)$")


def _entries(index_path: Path) -> List[Dict[str, Any]]:
    data = json.loads(index_path.read_text())
    if isinstance(data, dict):
        return data.get("entries", data.get("teachings", []))
    return data


def classify(entries: List[Dict[str, Any]],
             absorbed_hints: Optional[set] = None) -> Dict[str, List[Dict[str, Any]]]:
    absorbed_hints = absorbed_hints or set()
    out = {"KEEP": [], "ABSORBED": [], "STALE": [], "DUPLICATE": []}

    # Build version map: stem -> highest version seen.
    best_ver: Dict[str, int] = {}
    for e in entries:
        m = VER_RE.match(e.get("id", ""))
        if m:
            stem, n = m.group("stem"), int(m.group("n"))
            best_ver[stem] = max(best_ver.get(stem, 0), n)

    for e in entries:
        eid = e.get("id", "")
        title = (e.get("title") or "").strip()
        verdict = None
        reason = ""

        # DUPLICATE: an older version exists alongside a newer one.
        m = VER_RE.match(eid)
        if m and int(m.group("n")) < best_ver.get(m.group("stem"), 0):
            verdict, reason = "DUPLICATE", f"superseded by {m.group('stem')}-v{best_ver[m.group('stem')]}"

        # STALE: dated/no-title/event-signal stubs.
        if verdict is None:
            if not title or any(p.search(eid) for p in STALE_PATTERNS):
                verdict, reason = "STALE", ("no title (unpublishable)" if not title
                                            else "raw event signal / dated stub")

        # ABSORBED: flagged by the caller's hint list (confirm against harness).
        if verdict is None and eid in absorbed_hints:
            verdict, reason = "ABSORBED", "flagged absorbed (confirm against harness files)"

        if verdict is None:
            verdict, reason = "KEEP", "unabsorbed behavior"

        rec = {"id": eid, "title": title, "verdict": verdict, "reason": reason,
               "file": e.get("file")}
        out[verdict].append(rec)

    return out


def plan(index_path: Path, absorbed_hints: Optional[set] = None,
         cap: int = 10) -> Dict[str, Any]:
    entries = _entries(index_path)
    buckets = classify(entries, absorbed_hints)
    keep_n = len(buckets["KEEP"])
    return {
        "total": len(entries),
        "counts": {k: len(v) for k, v in buckets.items()},
        "cap": cap,
        "keep_within_cap": keep_n <= cap,
        "over_by": max(0, keep_n - cap),
        "buckets": buckets,
        "note": ("KEEP exceeds the cap — promote only the highest-value <=%d to "
                 "patches/ and route the rest to a base cut." % cap) if keep_n > cap else "KEEP within cap.",
    }


def _main(argv: List[str]) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Teaching reconciliation classifier")
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--index", required=True)
    pl.add_argument("--absorbed-hints", default=None, help="JSON list of ids to propose ABSORBED")
    pl.add_argument("--cap", type=int, default=10)
    args = p.parse_args(argv)

    if args.cmd == "plan":
        hints = set()
        if args.absorbed_hints:
            raw = Path(args.absorbed_hints).read_text() if Path(args.absorbed_hints).exists() else args.absorbed_hints
            hints = set(json.loads(raw))
        out = plan(Path(args.index), hints, args.cap)
        print(json.dumps(out, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
