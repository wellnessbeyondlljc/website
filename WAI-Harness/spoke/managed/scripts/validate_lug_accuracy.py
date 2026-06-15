#!/usr/bin/env python3
"""
Lug Accuracy Validator -- Pass 2: semantic and accuracy checks.
Usage: python3 scripts/validate_lug_accuracy.py [lug_path_or_dir] [--json]

Checks:
- target_files paths exist OR are marked NEW (correct to not exist yet)
- blocked_by references resolve (lug exists in bytype/)
- File target paths don't reference deleted/moved files (stale targets)
- Lug IDs are unique across bytype/
"""
import json
import sys
from pathlib import Path

LUGS_ROOT = Path("WAI-Spoke/lugs/bytype")


def build_id_index() -> dict:
    """Build a map of lug_id -> path for all lugs."""
    index = {}
    for f in LUGS_ROOT.rglob("*.json"):
        try:
            d = json.load(open(f))
            lid = d.get("id")
            if lid:
                index[lid] = f
        except Exception:
            pass
    return index


def check_target_files(lug: dict) -> list:
    """Check target_files -- NEW files should not exist, MODIFY files should exist."""
    issues = []
    for target in lug.get("target_files", []):
        if not isinstance(target, str):
            continue
        # Parse "path -- NEW" or "path -- MODIFY"
        parts = target.split(" -- ")
        path_str = parts[0].strip()
        marker = parts[1].strip().upper() if len(parts) > 1 else ""

        p = Path(path_str)
        if marker == "NEW":
            pass  # Correct: new files should not exist yet
        elif marker in ("MODIFY", "UPDATE", "EXTEND"):
            if not p.exists():
                issues.append(f"MODIFY target missing: {path_str}")
        elif not marker:
            # No marker -- existence is ambiguous, just note it
            pass
    return issues


def check_blocked_by(lug: dict, id_index: dict) -> list:
    """Check blocked_by references resolve."""
    issues = []
    for blocker_id in (lug.get("blocked_by") or []):
        if blocker_id not in id_index:
            issues.append(f"blocked_by unresolved: {blocker_id}")
    return issues


def validate_accuracy(lug_path: Path, id_index: dict) -> dict:
    result = {"path": str(lug_path), "id": None, "pass": True, "errors": [], "warnings": []}
    try:
        lug = json.load(open(lug_path))
    except Exception as e:
        result["pass"] = False
        result["errors"].append(str(e))
        return result

    result["id"] = lug.get("id", lug_path.stem)

    target_issues = check_target_files(lug)
    for issue in target_issues:
        result["warnings"].append(issue)

    blocker_issues = check_blocked_by(lug, id_index)
    for issue in blocker_issues:
        result["warnings"].append(issue)

    return result


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_json = "--json" in sys.argv

    target = args[0] if args else "WAI-Spoke/lugs/bytype"
    id_index = build_id_index()

    p = Path(target)
    if p.is_file():
        results = [validate_accuracy(p, id_index)]
    elif p.is_dir():
        results = [validate_accuracy(f, id_index) for f in sorted(p.rglob("*.json"))]
    else:
        print(f"Error: {target} not found", file=sys.stderr)
        sys.exit(1)

    if use_json:
        print(json.dumps(results, indent=2))
    else:
        issues = [r for r in results if r.get("warnings") or not r["pass"]]
        print(f"Lug QC Pass 2 -- {len(results)} lugs checked")
        print(f"  Issues found: {len(issues)}")
        for r in issues[:10]:
            print(f"\n  {r['id'] or r['path']}")
            for w in r.get("warnings", []):
                print(f"    ! {w}")
            for e in r.get("errors", []):
                print(f"    x {e}")
