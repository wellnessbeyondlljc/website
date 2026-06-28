#!/usr/bin/env python3
"""qa_suite_health.py - stale-test detection + gap taxonomy (spec-verification-quality-v1).

compute_coverage.py answers "how much is tested + what's the certification_score".
This answers the q2_coverage_maintenance freshness rule and the gap_taxonomy that
compute_coverage does not: a test that PASSED 90 days ago at an old version is a
coverage gap even though it once went green, and the three honest-gap types
(test-null, stale, failing) must be SURFACED as typed deficiencies, not hidden
inside an aggregate.

It reuses compute_coverage.aggregate_coverage for the cert math and adds:
  - stale_tests : a once-green (result==1) covering test whose lug's last-
                  verification timestamp is older than stale_days. Staleness is a
                  gap even on a green test (the spec's explicit rule).
  - null_checks : checks with result==null - disclosed honest gaps, never hidden.
  - failing     : checks with result==0.
  - gap_summary : {test_null, stale, failing} counts - the gap-taxonomy surface.

The intended per-test registry (test-manifest.json, last_run per test) does not
exist yet, so staleness uses the available, honest proxy: the lug's last-
verification timestamp = max(covering test result_ts/verified_at) else the lug's
completed_at/updated_at.

Pure core: compute_qa_health(lugs, now, stale_days). read_qa_health(spoke) scans
the v4 lug tree. Degrades to a zeroed-but-valid structure (never raises).
"""
import argparse
import glob
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compute_coverage import aggregate_coverage

DEFAULT_STALE_DAYS = 60


def _parse_ts(s):
    if isinstance(s, (int, float)):
        return float(s)
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _test_ts(test, lug):
    """Best last-verification timestamp for a check: the test's own result_ts /
    verified_at if present, else the lug's completed_at / updated_at (proxy)."""
    return (_parse_ts(test.get("result_ts"))
            or _parse_ts(test.get("verified_at"))
            or _parse_ts(lug.get("completed_at"))
            or _parse_ts(lug.get("updated_at")))


def _test_name(test):
    return test.get("name") or test.get("test_id") or test.get("assertion") or test.get("covers_ac") or "?"


def compute_qa_health(lugs, now=None, stale_days=DEFAULT_STALE_DAYS):
    """Coverage/cert (reused) + the three honest-gap types over v4 lugs."""
    if now is None:
        now = time.time()
    now = _parse_ts(now) if isinstance(now, str) else float(now)
    coverage = aggregate_coverage(lugs)

    stale_tests, null_checks, failing = [], [], []
    cutoff = stale_days * 86400
    for lug in lugs:
        if lug.get("schema_version") != 4:
            continue
        lid = lug.get("id")
        for t in lug.get("verification_test") or []:
            r = t.get("result")
            name = _test_name(t)
            if r == 0:
                failing.append({"lug_id": lid, "test": name, "covers_ac": t.get("covers_ac")})
            elif r != 1:   # null / missing -> honest unverified gap
                null_checks.append({"lug_id": lid, "test": name, "covers_ac": t.get("covers_ac")})
            else:          # green: a once-green test can still be STALE
                ts = _test_ts(t, lug)
                if ts is not None and (now - ts) > cutoff:
                    stale_tests.append({
                        "lug_id": lid, "test": name, "covers_ac": t.get("covers_ac"),
                        "age_days": round((now - ts) / 86400, 1)})

    gap_summary = {"test_null": len(null_checks), "stale": len(stale_tests), "failing": len(failing)}
    return {
        "coverage": coverage,
        "stale_tests": stale_tests,
        "null_checks": null_checks,
        "failing": failing,
        "gap_summary": gap_summary,
        "stale_days": stale_days,
        "status": "ok" if coverage.get("lug_count") else "no-v4-lugs-yet",
    }


def _spoke(spoke_path):
    """Base whose lugs/bytype holds the live lugs, base-aware. PRE-FIX it blindly appended
    'WAI-Spoke' -> on a v4 spoke QA health scanned a nonexistent path and was always empty
    (impl-fix-p1-silent-dead-v4-paths-v1)."""
    import os
    p = Path(spoke_path)
    if p.name in ("WAI-Spoke", "local"):
        return p
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import wai_paths
        base, mode = wai_paths.resolve_wai_root(str(p))
        if base and mode != "none":
            return Path(base)
    except Exception:
        pass
    return p / "WAI-Spoke"


def read_qa_health(spoke_path=".", now=None, stale_days=DEFAULT_STALE_DAYS):
    """Scan v4 lugs and compute QA suite health. Graceful: zeroed-but-valid on any
    failure so it never blocks brief generation."""
    try:
        spoke = _spoke(spoke_path)
        lugs = []
        for f in glob.glob(str(spoke / "lugs" / "bytype" / "**" / "*.json"), recursive=True):
            try:
                lugs.append(json.load(open(f)))
            except (OSError, json.JSONDecodeError):
                continue
        return compute_qa_health(lugs, now=now, stale_days=stale_days)
    except Exception:
        return {"coverage": {}, "stale_tests": [], "null_checks": [], "failing": [],
                "gap_summary": {"test_null": 0, "stale": 0, "failing": 0},
                "stale_days": stale_days, "status": "unreadable"}


def main(argv):
    ap = argparse.ArgumentParser(description="QA suite health: stale tests + gap taxonomy over v4 lugs.")
    ap.add_argument("--spoke-path", default=".")
    ap.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    args = ap.parse_args(argv)
    print(json.dumps(read_qa_health(args.spoke_path, stale_days=args.stale_days), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
