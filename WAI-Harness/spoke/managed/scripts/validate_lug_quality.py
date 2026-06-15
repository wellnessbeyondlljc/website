#!/usr/bin/env python3
"""
Lug Quality Validator -- Pass 1: mechanical field and path checks.
Usage: python3 scripts/validate_lug_quality.py [lug_path_or_dir] [--json]

Checks:
- Required fields present: id, type, status, title, perceive, execute, verify
- execute.steps is a non-empty list
- verify.done_when is a non-empty list
- target_files present and non-empty for impl/feature/task types
- effort field present
- model_fit present
- No placeholder text ("TODO", "TBD", "<fill>", "placeholder")
"""
import json
import sys
import os
from pathlib import Path

REQUIRED_FIELDS = ["id", "type", "status", "title", "perceive", "execute", "verify"]
PLACEHOLDER_PATTERNS = ["TODO", "TBD", "<fill>", "placeholder", "FIXME", "<tbd>"]
IMPL_TYPES = ["implementation", "feature", "task"]


def validate_lug(lug_path: Path) -> dict:
    result = {"path": str(lug_path), "id": None, "pass": True, "errors": [], "warnings": []}

    try:
        with open(lug_path) as f:
            lug = json.load(f)
    except json.JSONDecodeError as e:
        result["pass"] = False
        result["errors"].append(f"Invalid JSON: {e}")
        return result

    result["id"] = lug.get("id", lug_path.stem)
    lug_type = lug.get("type", "")

    # Required fields
    for field in REQUIRED_FIELDS:
        if field not in lug:
            result["errors"].append(f"Missing required field: {field}")
            result["pass"] = False

    # execute.steps non-empty
    execute = lug.get("execute", {})
    if isinstance(execute, dict):
        steps = execute.get("steps", [])
        if not steps:
            result["errors"].append("execute.steps is empty or missing")
            result["pass"] = False

    # verify.done_when non-empty
    verify = lug.get("verify", {})
    if isinstance(verify, dict):
        done_when = verify.get("done_when", [])
        if not done_when:
            result["errors"].append("verify.done_when is empty or missing")
            result["pass"] = False

    # target_files for impl types
    if lug_type in IMPL_TYPES:
        if not lug.get("effort"):
            result["warnings"].append("Missing effort field")
        if not lug.get("model_fit"):
            result["warnings"].append("Missing model_fit field")
        target_files = lug.get("target_files", [])
        if not target_files:
            result["warnings"].append("No target_files defined for impl/feature/task lug")

    # Placeholder text scan
    lug_str = json.dumps(lug)
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern in lug_str:
            result["warnings"].append(f"Placeholder text found: '{pattern}'")

    return result


def validate_path(target: str) -> list:
    p = Path(target)
    if p.is_file():
        return [validate_lug(p)]
    elif p.is_dir():
        results = []
        for f in sorted(p.rglob("*.json")):
            try:
                results.append(validate_lug(f))
            except Exception as e:
                results.append({"path": str(f), "pass": False, "errors": [str(e)], "warnings": []})
        return results
    else:
        print(f"Error: {target} not found", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_json = "--json" in sys.argv

    target = args[0] if args else "WAI-Spoke/lugs/bytype"
    results = validate_path(target)

    if use_json:
        print(json.dumps(results, indent=2))
    else:
        passed = sum(1 for r in results if r["pass"])
        failed = sum(1 for r in results if not r["pass"])
        warnings = sum(len(r.get("warnings", [])) for r in results)
        print(f"Lug QC Pass 1 -- {len(results)} lugs checked")
        print(f"  Passed: {passed}  Failed: {failed}  Warnings: {warnings}")
        for r in results:
            if not r["pass"]:
                print(f"\n  FAIL: {r['id'] or r['path']}")
                for e in r["errors"]:
                    print(f"    x {e}")
            if r.get("warnings"):
                for w in r["warnings"][:2]:  # cap at 2 warnings per lug
                    print(f"    ! {r['id'] or r['path']}: {w}")
