#!/usr/bin/env python3
"""
spoke_parity_check.py — Assertion-based parity verification

Reads hub/WAI-Hub/parity/head.json, then asserts each patch has been
applied to the target spoke. Parity is COMPUTED, never stamped.

Exit codes: 0 = at parity, 1 = behind parity, 2 = error
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wai_paths


def load_parity_head(hub_path: Path) -> dict:
    head_file = hub_path / "WAI-Hub" / "parity" / "head.json"
    if not head_file.exists():
        raise FileNotFoundError(f"Parity head not found: {head_file}")
    with open(head_file) as f:
        return json.load(f)


def check_hook_absolute_paths(spoke_path: Path) -> tuple[bool, str]:
    """Patch: hook-absolute-paths — no $CLAUDE_PROJECT_DIR in settings.json."""
    settings = spoke_path / ".claude" / "settings.json"
    if not settings.exists():
        return False, ".claude/settings.json missing"
    with open(settings) as f:
        content = f.read()
    if "$CLAUDE_PROJECT_DIR" in content:
        matches = re.findall(r'"command":\s*"([^"]*\$CLAUDE_PROJECT_DIR[^"]*)"', content)
        detail = f"Found in {len(matches)} hook command(s)"
        return False, detail
    return True, "No $CLAUDE_PROJECT_DIR in hook commands"


# Registry of assertion functions per patch ID
PATCH_ASSERTIONS = {
    "hook-absolute-paths": check_hook_absolute_paths,
}


def check_spoke(spoke_path: Path, hub_path: Path, verbose: bool = True) -> dict:
    spoke_path = Path(spoke_path)
    hub_path = Path(hub_path)

    try:
        head = load_parity_head(hub_path)
    except FileNotFoundError as e:
        return {"error": str(e), "parity": None, "spoke_parity": None, "at_parity": False, "gaps": []}

    head_parity = head.get("parity", 0)
    patches = head.get("patches", [])

    results = []
    gaps = []
    spoke_parity_level = 0

    for patch in patches:
        patch_id = patch["id"]
        patch_parity = patch.get("parity", 0)
        assertion_fn = PATCH_ASSERTIONS.get(patch_id)

        if assertion_fn is None:
            # No assertion function — assume unknown
            results.append({
                "patch": patch_id,
                "parity": patch_parity,
                "passed": None,
                "detail": "No assertion implemented for this patch"
            })
            continue

        passed, detail = assertion_fn(spoke_path)
        results.append({
            "patch": patch_id,
            "parity": patch_parity,
            "passed": passed,
            "detail": detail
        })

        if passed:
            spoke_parity_level = max(spoke_parity_level, patch_parity)
        else:
            gaps.append({"patch": patch_id, "parity": patch_parity, "detail": detail})

    at_parity = len(gaps) == 0 and head_parity > 0

    if verbose:
        print(f"Parity head: {head_parity} ({len(patches)} patches)")
        print(f"Spoke:       {spoke_path}")
        print()
        for r in results:
            status = "✓" if r["passed"] else ("?" if r["passed"] is None else "✗")
            print(f"  [{status}] {r['patch']} (parity {r['parity']}): {r['detail']}")
        print()
        if at_parity:
            print(f"  AT PARITY ({spoke_parity_level}/{head_parity})")
        else:
            print(f"  BEHIND PARITY: {len(gaps)} gap(s)")
            for g in gaps:
                print(f"    - {g['patch']}: {g['detail']}")

    return {
        "parity_head": head_parity,
        "spoke_parity": spoke_parity_level,
        "at_parity": at_parity,
        "gaps": gaps,
        "results": results
    }


def main():
    parser = argparse.ArgumentParser(description="Check spoke parity against hub head")
    parser.add_argument("spoke_path", nargs="?", default=".", help="Path to spoke (default: .)")
    parser.add_argument("--hub", help="Path to hub (default: read from WAI-State.json)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable")
    parser.add_argument("--quiet", action="store_true", help="Suppress output, use exit code only")
    args = parser.parse_args()

    spoke_path = Path(args.spoke_path).resolve()

    # Resolve hub path
    hub_path = args.hub
    if not hub_path:
        base, _mode = wai_paths.resolve_wai_root(str(spoke_path))
        state_file = Path(base) / "WAI-State.json" if base is not None else None
        if state_file is not None and state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
            hub_path = state.get("wheel", {}).get("hub_path", "")
    if not hub_path:
        print("ERROR: hub path not found. Pass --hub or set wheel.hub_path in WAI-State.json", file=sys.stderr)
        sys.exit(2)

    verbose = not args.quiet and not args.json
    result = check_spoke(spoke_path, hub_path, verbose=verbose)

    if "error" in result:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(result, indent=2))

    sys.exit(0 if result["at_parity"] else 1)


if __name__ == "__main__":
    main()
