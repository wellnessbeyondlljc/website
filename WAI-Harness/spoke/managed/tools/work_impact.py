#!/usr/bin/env python3
"""work_impact.py — "where did the valuable time go?" analytics from git numstat.

Single source of truth: git. For a commit range it reads `git diff --numstat` (lines
added/removed per file) + `git diff --name-status` (A/M/D = created/updated/deleted),
then classifies each changed path into a *work type* (scout expedition / lug work /
advisor time / teaching / framework / docs / state / other). The output is a compact
JSON "work-impact" record plus a human "perspective" that ranks where the most
valuable effort landed and flags churn (effort with little net output).

Designed to be called per-spoke by the Minder tender / Autopilot dashboard so a fleet
run can show, at a glance: scout vs lug vs advisor time, and the CRUD footprint on each
spoke.

Schema: work-impact-v1 (see work-impact.schema.json).

Usage:
    python3 work_impact.py --repo /path/to/spoke --last 50
    python3 work_impact.py --repo . --since 2026-06-01
    python3 work_impact.py --repo . --range HEAD~20..HEAD
    python3 work_impact.py --repo . --last 50 --json   # machine output only
"""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "work-impact-v1"

# ---------------------------------------------------------------------------
# Work-type classification (ordered: first matching rule wins)
# A rule is (work_type, [substring fragments matched against the lowercased path]).
# Path-based so a single source (git) yields both the work split AND the CRUD impact.
# ---------------------------------------------------------------------------
CLASSIFY_RULES: List[Tuple[str, List[str]]] = [
    ("scout",     ["/scout", "scout-", "scouts/", "expedition", "/recon", "wayfinder"]),
    ("advisor",   ["/advisors/", "/advisor/", "advisor_", "scan_state", "findings-log"]),
    ("lug",       ["/lugs/", "lugindex", "work-queue", "ready-queue", "refinement-queue"]),
    ("teaching",  ["/teachings", "teaching", "/learnings/", "signal-"]),
    ("initiative",["/initiatives/", "initiative_"]),
    ("session",   ["/sessions/", "track.jsonl", "session-summary", "/bolts/", "savepoint"]),
    ("state",     ["wai-state.json", "registry.json", "schedule-index", "index.json", "scan_state.json"]),
    ("framework", ["/managed/tools/", "/managed/schemas/", "/scripts/", ".claude/", "/hooks/"]),
    ("docs",      [".md", "/docs/", "readme", "changelog", "agents.md"]),
]
DEFAULT_TYPE = "other"

# Relative "value weight" per type — used only for the perspective ranking, not the
# raw counts. Lug/initiative/framework changes are treated as higher-leverage output;
# advisor/session/state churn is lower-leverage. Tunable.
VALUE_WEIGHT = {
    "lug": 1.0, "initiative": 1.0, "framework": 0.9, "teaching": 0.8,
    "scout": 0.7, "docs": 0.5, "advisor": 0.4, "session": 0.2,
    "state": 0.15, "other": 0.5,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify(path: str) -> str:
    p = path.lower()
    for work_type, frags in CLASSIFY_RULES:
        if any(f in p for f in frags):
            return work_type
    return DEFAULT_TYPE


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------

def _git(repo: Path, args: List[str]) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {out.stderr.strip()[:200]}")
    return out.stdout


def _resolve_range(repo: Path, last: Optional[int], since: Optional[str],
                   rng: Optional[str]) -> Tuple[str, Dict[str, Any]]:
    """Return (diff_spec, range_meta). diff_spec is what we pass to git diff/log."""
    if rng:
        spec = rng
    elif since:
        # commits since a date → first such commit's parent..HEAD
        shas = _git(repo, ["log", f"--since={since}", "--format=%H"]).split()
        if not shas:
            return "", {"commits": 0, "since": since, "from": None, "to": None}
        oldest = shas[-1]
        spec = f"{oldest}~1..HEAD" if _has_parent(repo, oldest) else _empty_tree(repo) + "..HEAD"
    else:
        n = last or 50
        spec = f"HEAD~{n}..HEAD" if _commit_count(repo) > n else _empty_tree(repo) + "..HEAD"
    # meta
    commits = _git(repo, ["rev-list", "--count", spec]).strip()
    try:
        commit_n = int(commits)
    except ValueError:
        commit_n = 0
    from_to = spec.split("..") if ".." in spec else [None, spec]
    return spec, {
        "spec": spec, "commits": commit_n,
        "from": from_to[0], "to": from_to[1] if len(from_to) > 1 else "HEAD",
        "since": since,
    }


def _commit_count(repo: Path) -> int:
    try:
        return int(_git(repo, ["rev-list", "--count", "HEAD"]).strip())
    except Exception:
        return 0


def _has_parent(repo: Path, sha: str) -> bool:
    try:
        _git(repo, ["rev-parse", "--verify", f"{sha}~1"])
        return True
    except Exception:
        return False


def _empty_tree(repo: Path) -> str:
    # git's well-known empty tree object — lets us diff the very first commit
    return _git(repo, ["hash-object", "-t", "tree", "/dev/null"]).strip()


# ---------------------------------------------------------------------------
# core
# ---------------------------------------------------------------------------

def _blank() -> Dict[str, int]:
    return {"files": 0, "created": 0, "updated": 0, "deleted": 0,
            "lines_added": 0, "lines_removed": 0}


def analyze(repo: Path, last: Optional[int] = None, since: Optional[str] = None,
            rng: Optional[str] = None, spoke_id: str = "") -> Dict[str, Any]:
    spec, meta = _resolve_range(repo, last, since, rng)
    by_type: Dict[str, Dict[str, int]] = {}
    totals = _blank()

    if spec:
        # name-status → CRUD letter per file
        status_map: Dict[str, str] = {}
        for line in _git(repo, ["diff", "--name-status", spec]).splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            code = parts[0][0]  # A/M/D/R/C
            fname = parts[-1]   # for renames, the new name is last
            status_map[fname] = code
        # numstat → lines per file
        for line in _git(repo, ["diff", "--numstat", spec]).splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            added_s, removed_s, fname = parts[0], parts[1], parts[-1]
            added = 0 if added_s == "-" else int(added_s)
            removed = 0 if removed_s == "-" else int(removed_s)
            wt = classify(fname)
            bucket = by_type.setdefault(wt, _blank())
            code = status_map.get(fname, "M")
            crud = {"A": "created", "D": "deleted"}.get(code, "updated")
            for tgt in (bucket, totals):
                tgt["files"] += 1
                tgt[crud] += 1
                tgt["lines_added"] += added
                tgt["lines_removed"] += removed

    # derive shares + net + value score
    grand_net = sum(b["lines_added"] + b["lines_removed"] for b in by_type.values()) or 1
    enriched: Dict[str, Dict[str, Any]] = {}
    for wt, b in by_type.items():
        churn = b["lines_added"] + b["lines_removed"]
        enriched[wt] = {
            **b,
            "net_lines": b["lines_added"] - b["lines_removed"],
            "churn_lines": churn,
            "share_pct": round(100 * churn / grand_net, 1),
            "value_score": round(churn * VALUE_WEIGHT.get(wt, 0.5), 1),
        }

    return {
        "schema": SCHEMA,
        "spoke_id": spoke_id or repo.name,
        "repo": str(repo),
        "range": meta,
        "generated_at": now_iso(),
        "totals": {**totals,
                   "net_lines": totals["lines_added"] - totals["lines_removed"],
                   "churn_lines": totals["lines_added"] + totals["lines_removed"]},
        "by_work_type": enriched,
        "perspective": _perspective(enriched, totals),
    }


def _perspective(enriched: Dict[str, Dict[str, Any]], totals: Dict[str, int]) -> Dict[str, Any]:
    if not enriched:
        return {"headline": "No changes in range.", "ranked": [], "signals": []}
    ranked = sorted(enriched.items(), key=lambda kv: kv[1]["value_score"], reverse=True)
    top_wt, top = ranked[0]
    headline = (f"Most valuable use of time: {top_wt} work "
                f"({top['share_pct']}% of change, {top['files']} files, "
                f"+{top['lines_added']}/-{top['lines_removed']} lines)")
    signals: List[str] = []
    # churn signal: lots of change in a low-leverage type
    for wt in ("advisor", "session", "state"):
        b = enriched.get(wt)
        if b and b["share_pct"] >= 30:
            signals.append(
                f"{b['share_pct']}% of change is {wt} churn — high overhead relative to output")
    # output signal: little or no lug/initiative output
    productive = sum(enriched.get(wt, {}).get("churn_lines", 0)
                     for wt in ("lug", "initiative", "framework"))
    if totals["lines_added"] + totals["lines_removed"] > 0 and productive == 0:
        signals.append("Zero lug/initiative/framework output in this window — activity but no durable work landed")
    return {
        "headline": headline,
        "ranked": [{"work_type": wt, **{k: v[k] for k in
                    ("share_pct", "value_score", "files", "net_lines", "created", "updated", "deleted")}}
                   for wt, v in ranked],
        "signals": signals,
    }


def render(report: Dict[str, Any]) -> str:
    r = report["range"]
    lines = []
    lines.append(f"── Work Impact: {report['spoke_id']}  ({r.get('commits', 0)} commits, {r.get('spec','')})")
    t = report["totals"]
    lines.append(f"   CRUD: +{t['created']} created / ~{t['updated']} updated / -{t['deleted']} deleted "
                 f"files   ({t['files']} files, +{t['lines_added']}/-{t['lines_removed']} lines)")
    lines.append("   " + "─" * 60)
    lines.append(f"   {'work type':<12}{'share':>7}{'files':>7}{'+lines':>8}{'-lines':>8}  CRUD(c/u/d)")
    for row in report["perspective"]["ranked"]:
        wt = row["work_type"]
        b = report["by_work_type"][wt]
        lines.append(f"   {wt:<12}{str(row['share_pct'])+'%':>7}{b['files']:>7}"
                     f"{b['lines_added']:>8}{b['lines_removed']:>8}  "
                     f"{b['created']}/{b['updated']}/{b['deleted']}")
    lines.append("   " + "─" * 60)
    lines.append(f"   ▶ {report['perspective']['headline']}")
    for s in report["perspective"]["signals"]:
        lines.append(f"   ⚠ {s}")
    return "\n".join(lines)


def _spoke_id(repo: Path) -> str:
    wp = Path(__file__).resolve().parent / "wai_paths.py"
    try:
        out = subprocess.run(["python3", str(wp), "--root", str(repo), "--json"],
                             capture_output=True, text=True, timeout=15)
        if out.returncode == 0:
            base = json.loads(out.stdout).get("_base", "")
            state = Path(base) / "WAI-State.json"
            if state.exists():
                d = json.loads(state.read_text())
                return (d.get("wheelwright", {}) or {}).get("wheel_id") or d.get("wheelwright", {}).get("name") or repo.name
    except Exception:
        pass
    return repo.name


def _main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Work-impact analytics from git numstat")
    p.add_argument("--repo", default=".")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--last", type=int, help="last N commits (default 50)")
    g.add_argument("--since", help="commits since ISO date, e.g. 2026-06-01")
    g.add_argument("--range", dest="rng", help="explicit git range A..B")
    p.add_argument("--json", action="store_true", help="emit JSON only")
    args = p.parse_args(argv)

    repo = Path(args.repo).resolve()
    report = analyze(repo, last=args.last, since=args.since, rng=args.rng,
                     spoke_id=_spoke_id(repo))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
        print()
        print(json.dumps(report, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
