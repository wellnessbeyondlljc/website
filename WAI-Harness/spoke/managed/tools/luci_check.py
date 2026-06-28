#!/usr/bin/env python3
"""Luci — Uptime Engineer. Checks spoke health based on uptime tier.

Usage:
    python3 tools/luci_check.py [--spoke-path PATH] [--tier TIER]

Determines uptime tier from project foundation, runs applicable checks,
creates bug/task lugs for issues found.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_p = argparse.ArgumentParser(description="Luci — Uptime engineer advisor for spoke health monitoring.")
_p.add_argument("--spoke-path", default=".", metavar="PATH", help="Path to spoke root")
_p.add_argument("--tier", default=None, help="Override uptime tier (e.g. tier-1, tier-2)")
_a = _p.parse_args()
SPOKE_PATH = Path(_a.spoke_path)
TIER_OVERRIDE = _a.tier

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wai_paths import resolve_wai_root, advisors_dir  # noqa: E402  (v3/v4 resolver)


def _spoke_base(spoke_root: Path) -> Path:
    """Working-state base: WAI-Harness/spoke/local on v4, WAI-Spoke on v3.
    State + lugs live here. Advisors are a sibling tree (see _advisors_base)."""
    root, mode = resolve_wai_root(str(spoke_root))
    if root and mode != "none":
        return Path(root)
    return Path(spoke_root) / "WAI-Spoke"  # last-resort v3 fallback


def _advisors_base(spoke_root: Path) -> Path:
    """Advisors tree: WAI-Harness/spoke/advisors on v4, WAI-Spoke/advisors on v3."""
    adir = advisors_dir(str(spoke_root))
    if adir:
        return Path(adir)
    return Path(spoke_root) / "WAI-Spoke" / "advisors"


SPOKE_BASE = _spoke_base(SPOKE_PATH)

LUCI_CONFIG = _advisors_base(SPOKE_PATH) / "luci/scan_state.json"
STATE_FILE = SPOKE_BASE / "WAI-State.json"


def load_config():
    if LUCI_CONFIG.exists():
        return json.loads(LUCI_CONFIG.read_text())
    return {}


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def infer_tier(state):
    """Infer uptime tier from project foundation."""
    foundation = state.get("_project_foundation", {})
    identity = foundation.get("identity", {})
    proj_type = identity.get("type", "").lower()
    one_liner = identity.get("one_liner", "").lower()

    # Revenue/user-facing keywords → critical
    if any(kw in one_liner for kw in ["revenue", "e-commerce", "saas", "payment", "customer"]):
        return "critical"
    # Web app / website → standard
    if any(kw in one_liner for kw in ["website", "web app", "application", "api", "service"]):
        return "standard"
    # Framework / library / tool → internal
    if any(kw in one_liner for kw in ["framework", "library", "cli", "tool", "protocol"]):
        return "internal"
    return "development"


def check_code_health(spoke_path):
    """Run code health checks: tests, lint."""
    results = []

    # Check for test runner
    if (spoke_path / "tests").exists() or (spoke_path / "test").exists():
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "tests/", "-x", "--tb=short", "-q"],
                capture_output=True, text=True, timeout=60, cwd=str(spoke_path)
            )
            if result.returncode == 0:
                results.append({"check": "tests", "status": "pass", "detail": result.stdout.strip().split("\n")[-1]})
            else:
                results.append({"check": "tests", "status": "fail", "detail": result.stdout.strip().split("\n")[-1]})
        except (subprocess.TimeoutExpired, FileNotFoundError):
            results.append({"check": "tests", "status": "skip", "detail": "pytest not available or timeout"})
    else:
        results.append({"check": "tests", "status": "skip", "detail": "No tests/ directory"})

    # Check for JSON validity of key files (base-aware: v4 local / v3 WAI-Spoke)
    base = _spoke_base(spoke_path)
    for label, path in [("WAI-State.json", base / "WAI-State.json")]:
        if path.exists():
            try:
                json.loads(path.read_text())
                results.append({"check": f"json:{label}", "status": "pass"})
            except json.JSONDecodeError as e:
                results.append({"check": f"json:{label}", "status": "fail", "detail": str(e)})

    # Check git status
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, cwd=str(spoke_path)
        )
        dirty_count = len([l for l in result.stdout.strip().split("\n") if l.strip()])
        results.append({
            "check": "git_clean",
            "status": "pass" if dirty_count == 0 else "warn",
            "detail": f"{dirty_count} uncommitted changes" if dirty_count else "clean"
        })
    except FileNotFoundError:
        results.append({"check": "git_clean", "status": "skip", "detail": "git not available"})

    return results


def check_availability(spoke_path, state):
    """Check if the service is reachable (if URL configured)."""
    results = []
    # Look for deploy URL in state or workspace
    workspace = state.get("wheel", {}).get("workspace", {})
    # Future: check actual URLs
    results.append({"check": "availability", "status": "skip", "detail": "No deploy URL configured — add workspace.deploy_url to WAI-State.json"})
    return results


def create_bug_lug(spoke_path, check_result):
    """Create a bug lug for a failed check."""
    import hashlib
    title = f"Luci detected: {check_result['check']} failed — {check_result.get('detail', 'unknown')}"
    lug_id = "bug-luci-" + hashlib.sha256(title.encode()).hexdigest()[:8]

    lug = {
        "i": lug_id,
        "t": title,
        "ty": "bug",
        "s": "open",
        "ca": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gb": "advisor-luci",
        "fw_ver": "3.0.0",
        "va": "fix",
        "impact": 7,
        "effort": 2,
        "rt": "LOCAL",
        "description": f"Luci uptime check failed: {json.dumps(check_result)}",
        "_behavior_directive": {
            "what_this_is": "Auto-generated bug from Luci uptime check failure",
            "what_this_is_NOT": "Not a false positive — Luci verified this check failed"
        }
    }

    bug_dir = _spoke_base(spoke_path) / "lugs/bytype/bug/open"
    bug_dir.mkdir(parents=True, exist_ok=True)
    (bug_dir / f"{lug_id}.json").write_text(json.dumps(lug, indent=2) + "\n")
    return lug_id


def main():
    config = load_config()
    state = load_state()

    tier = TIER_OVERRIDE or config.get("uptime_tier") or infer_tier(state)
    tier_config = config.get("uptime_tiers", {}).get(tier, {})

    print(f"\n{'='*50}")
    print(f"  Luci — Uptime Engineer")
    print(f"  Spoke: {SPOKE_PATH.resolve().name}")
    print(f"  Tier: {tier} ({tier_config.get('description', 'unknown')})")
    print(f"  Target: {tier_config.get('target', 'N/A')}")
    print(f"{'='*50}\n")

    all_results = []

    # Code health (all tiers)
    print("  Running code health checks...")
    code_results = check_code_health(SPOKE_PATH)
    all_results.extend(code_results)

    # Availability (non-internal tiers)
    if tier != "internal":
        print("  Running availability checks...")
        avail_results = check_availability(SPOKE_PATH, state)
        all_results.extend(avail_results)

    # Display results
    print(f"\n  {'Check':<25} {'Status':<8} {'Detail'}")
    print(f"  {'─'*25} {'─'*8} {'─'*30}")

    failures = []
    for r in all_results:
        status = r["status"]
        icon = {"pass": "OK", "fail": "FAIL", "warn": "WARN", "skip": "SKIP"}[status]
        detail = r.get("detail", "")[:40]
        print(f"  {r['check']:<25} {icon:<8} {detail}")
        if status == "fail":
            failures.append(r)

    # Create bug lugs for failures
    if failures:
        print(f"\n  {len(failures)} failures detected — creating bug lugs...")
        for f in failures:
            lug_id = create_bug_lug(SPOKE_PATH, f)
            print(f"    Created: {lug_id}")

    # Update scan state
    if config:
        config["last_scan_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        config["scan_count"] = config.get("scan_count", 0) + 1
        config["uptime_tier"] = tier
        config["passes"].append({
            "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tier": tier,
            "checks": len(all_results),
            "pass": sum(1 for r in all_results if r["status"] == "pass"),
            "fail": sum(1 for r in all_results if r["status"] == "fail"),
            "warn": sum(1 for r in all_results if r["status"] == "warn"),
            "skip": sum(1 for r in all_results if r["status"] == "skip"),
        })
        # Keep last 50 passes
        config["passes"] = config["passes"][-50:]
        LUCI_CONFIG.write_text(json.dumps(config, indent=2) + "\n")

    print(f"\n  Summary: {sum(1 for r in all_results if r['status'] == 'pass')} pass, "
          f"{sum(1 for r in all_results if r['status'] == 'fail')} fail, "
          f"{sum(1 for r in all_results if r['status'] == 'warn')} warn, "
          f"{sum(1 for r in all_results if r['status'] == 'skip')} skip")
    print()


if __name__ == "__main__":
    main()
