#!/usr/bin/env python3
"""Coverage + certification computation (spec-verification-quality-v1 q2, AC28/AC30).

Now that v4 lugs carry a structured verification_test array (AC<->test traceability),
suite health is computable: lug coverage %, AC coverage, null rate, and
certification_score = passes / (passes + fails + nulls). This is the data behind the
wakeup Quality Health section (AC30) and the QA advisor's view (AC28).

Pure core: aggregate_coverage(lugs) over a list of v4 lug dicts. read_coverage(spoke)
scans the lug tree. Degrades gracefully (returns a zeroed-but-valid structure) when no
v4 lugs exist yet, so it never blocks brief generation.
"""
import argparse
import glob
import json
import os
import sys
from pathlib import Path


def aggregate_coverage(lugs):
    """Aggregate coverage/certification over a list of v4 lug dicts.

    Returns: {
      lug_count, lugs_with_tests, lugs_fully_covered, ac_coverage_pct,
      test_count, passes, fails, nulls, null_rate, certification_score,
      uncertified_lugs: [ids with a null/fail test]
    }
    certification_score = passes/(passes+fails+nulls); null counts AGAINST it
    (an unrun test is not a pass — spec-verification-quality-v1).
    """
    lug_count = lugs_with_tests = lugs_fully_covered = 0
    total_acs = covered_acs = 0
    passes = fails = nulls = 0
    uncertified = []

    for lug in lugs:
        if lug.get("schema_version") != 4:
            continue
        lug_count += 1
        vt = lug.get("verification_test") or []
        if vt:
            lugs_with_tests += 1
        # per-AC coverage
        acs = lug.get("acceptance_criteria") or []
        covered_keys = set()
        for t in vt:
            ca = t.get("covers_ac")
            if ca:
                covered_keys.add(str(ca).split(None, 1)[0].rstrip(":"))
                covered_keys.add(str(ca).strip())
        lug_total = lug_covered = 0
        for ac in acs:
            key = (ac.get("id") or ac.get("text") or "") if isinstance(ac, dict) else str(ac)
            tok = key.strip().split(None, 1)[0] if key.strip() else ""
            if not tok:
                continue
            lug_total += 1
            if tok in covered_keys or key.strip() in covered_keys:
                lug_covered += 1
        total_acs += lug_total
        covered_acs += lug_covered
        if lug_total and lug_covered == lug_total:
            lugs_fully_covered += 1
        # result tally
        lug_has_gap = False
        for t in vt:
            r = t.get("result")
            if r == 1:
                passes += 1
            elif r == 0:
                fails += 1
                lug_has_gap = True
            else:
                nulls += 1
                lug_has_gap = True
        if lug_has_gap:
            uncertified.append(lug.get("id"))

    denom = passes + fails + nulls
    return {
        "lug_count": lug_count,
        "lugs_with_tests": lugs_with_tests,
        "lugs_fully_covered": lugs_fully_covered,
        "ac_coverage_pct": round(covered_acs / total_acs, 3) if total_acs else None,
        "test_count": denom,
        "passes": passes,
        "fails": fails,
        "nulls": nulls,
        "null_rate": round(nulls / denom, 3) if denom else None,
        "certification_score": round(passes / denom, 3) if denom else None,
        "uncertified_lugs": uncertified,
    }


def read_coverage(spoke_path="."):
    """Scan the lug tree for v4 lugs and aggregate. Graceful: zeroed structure if none."""
    spoke = Path(spoke_path)
    if spoke.name != "WAI-Spoke":
        spoke = spoke / "WAI-Spoke"
    lugs = []
    for f in glob.glob(str(spoke / "lugs" / "bytype" / "**" / "*.json"), recursive=True):
        try:
            lugs.append(json.load(open(f)))
        except (OSError, json.JSONDecodeError):
            continue
    health = aggregate_coverage(lugs)
    health["status"] = "ok" if health["lug_count"] else "no-v4-lugs-yet"
    return health


def main(argv):
    ap = argparse.ArgumentParser(description="Compute lug coverage + certification.")
    ap.add_argument("--spoke-path", default=".")
    args = ap.parse_args(argv)
    h = read_coverage(args.spoke_path)
    print(json.dumps(h, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
