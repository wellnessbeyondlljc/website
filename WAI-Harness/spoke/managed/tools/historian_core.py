#!/usr/bin/env python3
"""historian_core.py — lightweight zero-dependency lay-of-the-land survey (warmup step 1).

(impl-historian-core-survey-v1, spec-v4-migration-home-map-v1) ALWAYS survey
before migrating or aligning — even a v3 spoke; never assume the ground is level.
The full Historian advisor isn't deployed until warmup step 6, so step 1 runs
this standalone, stdlib-only scan to produce the baseline map that unblocks
coverage review, gap analysis, and the migration plan.

It satisfies v4_migrate's survey precondition (writes historian-survey.json) and
seeds the home_map four-bucket classification with heuristic suggestions (the
native agent / human confirms — these are not final).

CRITICAL completeness guard (spec completeness_audit): the survey reports its OWN
coverage — coverage_pct plus an explicit unscanned[] list. An unreadable entry is
a named gap, never a silent omission, so downstream steps see the gaps in the
survey itself rather than a false 'complete'.

API:
  git_tracked(root) -> set(names)
  suggest_bucket(name) -> Preserve | Transform | Flag | Drop
  survey(root, now_iso=None, exclude=None) -> report
  write_survey(report, path) -> path
"""
import json
import os
import subprocess

SURVEY_NAME = "historian-survey.json"
_EPHEMERAL = ("autosave", ".autosave", "tmp", "temp", "cache", "__pycache__", ".pytest_cache")
_AMBIGUOUS_SUFFIX = (".template", ".bak", ".old")
_REGENERATED = ("index.jsonl", "-index.json", "index.json")


def git_tracked(root):
    """Top-level names git tracks under root. Empty set off-repo (never crashes)."""
    try:
        r = subprocess.run(["git", "-C", root, "ls-files"], capture_output=True, text=True)
        if r.returncode != 0:
            return set()
        return {line.split("/", 1)[0] for line in r.stdout.splitlines() if line}
    except Exception:
        return set()


def suggest_bucket(name):
    """Heuristic four-bucket suggestion (seed only; native agent/human confirms)."""
    low = name.lower()
    if low in _EPHEMERAL or any(low == e for e in _EPHEMERAL):
        return "Drop"
    if low.endswith(_AMBIGUOUS_SUFFIX):
        return "Flag"
    if low.endswith(_REGENERATED) or ("index" in low and low.endswith(".jsonl")):
        return "Transform"
    return "Preserve"


def _kind(path, name):
    low = name.lower()
    if os.path.isdir(path):
        return "dir"
    if low.endswith((".jsonl",)) and "index" in low:
        return "index"
    if low.startswith("wai-state"):
        return "state"
    if low.endswith((".yaml", ".yml", ".json")) and ("config" in low or "metadata" in low or low.endswith(".template")):
        return "config"
    return "file"


def survey(root, now_iso=None, exclude=None):
    """Scan the top level of `root`, classify each entry, report self-coverage +
    typed gaps. stdlib-only; safe to run at cold-start before any advisor exists."""
    exclude = set(exclude or [".git"])
    tracked = git_tracked(root)
    entries, unscanned, gaps = [], [], []
    by_kind = {}

    try:
        names = sorted(os.listdir(root))
    except OSError as e:
        return {"root": root, "generated_at": now_iso, "coverage_pct": 0.0,
                "scanned": [], "unscanned": [{"name": root, "reason": str(e)}],
                "entries": [], "gaps": [{"gap": "unreadable-root", "detail": str(e)}]}

    scanned = []
    for name in names:
        if name in exclude:
            continue
        path = os.path.join(root, name)
        try:
            is_dir = os.path.isdir(path)
            size = sum(os.path.getsize(os.path.join(dp, f))
                       for dp, _d, fs in os.walk(path) for f in fs) if is_dir \
                else os.path.getsize(path)
            kind = _kind(path, name)
            is_tracked = name in tracked
            entry = {"name": name, "kind": kind, "tracked": is_tracked,
                     "size": size, "suggested_bucket": suggest_bucket(name)}
            entries.append(entry)
            by_kind[kind] = by_kind.get(kind, 0) + 1
            scanned.append(name)
            # typed gaps
            if not is_tracked and not is_dir:
                gaps.append({"gap": "decision-undocumented", "name": name,
                             "detail": "untracked file (no git history / rationale)"})
            if is_dir and size == 0:
                gaps.append({"gap": "cruft/misplacement", "name": name, "detail": "empty directory"})
        except OSError as e:
            unscanned.append({"name": name, "reason": str(e)})

    total = len(scanned) + len(unscanned)
    coverage_pct = round(len(scanned) / total, 3) if total else 1.0
    return {"root": root, "generated_at": now_iso,
            "coverage_pct": coverage_pct, "scanned": scanned, "unscanned": unscanned,
            "entry_count": len(entries), "assets_by_kind": by_kind,
            "entries": entries, "gaps": gaps,
            "completeness_note": "coverage_pct < 1.0 means unscanned[] entries exist — "
                                 "downstream steps must treat those as unknown, not absent"}


def write_survey(report, path):
    """Persist the survey where v4_migrate.has_current_survey looks for it."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    json.dump(report, open(path, "w"), indent=2)
    return path


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="lightweight lay-of-the-land survey")
    ap.add_argument("root", nargs="?", default="WAI-Spoke")
    ap.add_argument("--now-iso", default=None)
    ap.add_argument("--out", default=None, help=f"write the survey to this path (default <root>/{SURVEY_NAME})")
    a = ap.parse_args(argv)
    rep = survey(a.root, a.now_iso)
    out = a.out or os.path.join(a.root, SURVEY_NAME)
    write_survey(rep, out)
    print(f"[historian_core] surveyed {rep['entry_count']} entries, coverage "
          f"{rep['coverage_pct']*100:.0f}%, {len(rep['gaps'])} gap(s) -> {out}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
