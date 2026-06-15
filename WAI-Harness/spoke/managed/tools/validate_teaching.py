#!/usr/bin/env python3
"""Teaching schema validator — enforces required fields per spec-teaching-delivery-system-v1.

Every teaching must carry: priority, adopt_asap, verification_steps, apply_steps.
verification_steps and apply_steps must be non-empty arrays with required sub-fields.
adopt_asap must be derived correctly from priority (P0/P1 -> True, P2/P3 -> False).

CLI:
  python3 tools/validate_teaching.py <teaching.json>
  exits 0 if valid, 1 with errors printed to stderr
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
HOT_PATCH_PRIORITIES = {"P0", "P1"}

VERIFICATION_STEP_FIELDS = {"id", "description", "check", "pass_criteria"}
APPLY_STEP_FIELDS = {"id", "description", "action"}


def validate_teaching(data: dict[str, Any]) -> list[str]:
    """Validate a teaching dict. Returns list of error strings (empty = valid)."""
    errors: list[str] = []

    # priority
    priority = data.get("priority")
    if priority is None:
        errors.append("missing required field: priority")
    elif priority not in VALID_PRIORITIES:
        errors.append(f"priority must be one of {sorted(VALID_PRIORITIES)}, got {priority!r}")

    # adopt_asap
    adopt_asap = data.get("adopt_asap")
    if adopt_asap is None:
        errors.append("missing required field: adopt_asap")
    elif not isinstance(adopt_asap, bool):
        errors.append(f"adopt_asap must be boolean, got {type(adopt_asap).__name__}")
    elif priority in VALID_PRIORITIES:
        expected = priority in HOT_PATCH_PRIORITIES
        if adopt_asap != expected:
            errors.append(
                f"adopt_asap derivation mismatch: priority={priority!r} requires "
                f"adopt_asap={expected}, got {adopt_asap}"
            )

    # verification_steps
    vsteps = data.get("verification_steps")
    if vsteps is None:
        errors.append("missing required field: verification_steps")
    elif not isinstance(vsteps, list):
        errors.append("verification_steps must be an array")
    elif len(vsteps) == 0:
        errors.append("verification_steps must have at least one item")
    else:
        for i, step in enumerate(vsteps):
            if not isinstance(step, dict):
                errors.append(f"verification_steps[{i}] must be an object")
                continue
            for field in VERIFICATION_STEP_FIELDS:
                if field not in step:
                    errors.append(f"verification_steps[{i}] missing required field: {field}")
                elif not isinstance(step[field], str):
                    errors.append(f"verification_steps[{i}].{field} must be a string")

    # apply_steps
    asteps = data.get("apply_steps")
    if asteps is None:
        errors.append("missing required field: apply_steps")
    elif not isinstance(asteps, list):
        errors.append("apply_steps must be an array")
    elif len(asteps) == 0:
        errors.append("apply_steps must have at least one item")
    else:
        for i, step in enumerate(asteps):
            if not isinstance(step, dict):
                errors.append(f"apply_steps[{i}] must be an object")
                continue
            for field in APPLY_STEP_FIELDS:
                if field not in step:
                    errors.append(f"apply_steps[{i}] missing required field: {field}")
                elif not isinstance(step[field], str):
                    errors.append(f"apply_steps[{i}].{field} must be a string")

    return errors


def validate_teaching_file(path: str | Path) -> list[str]:
    """Load a teaching JSON file and validate it. Returns error list."""
    p = Path(path)
    if not p.exists():
        return [f"file not found: {p}"]
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {e}"]
    if not isinstance(data, dict):
        return ["teaching must be a JSON object"]
    return validate_teaching(data)


def _main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: validate_teaching.py <teaching.json>", file=sys.stderr)
        return 2
    errors = validate_teaching_file(argv[0])
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"OK: {argv[0]} is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
