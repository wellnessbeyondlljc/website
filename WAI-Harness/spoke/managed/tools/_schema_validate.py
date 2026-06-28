"""
Shared minimal JSON-Schema draft-07 validator for framework tools.

Supports: required, const, pattern, types, minLength, minimum/maximum, enum,
nested object validation, additionalProperties:false. No external deps.
"""

from __future__ import annotations

import json
import re


def validate_dict(instance: dict, schema: dict) -> list[str]:
    """Validate `instance` against `schema` (already-parsed). Returns error list."""
    errors: list[str] = []

    for field in schema.get("required", []):
        if field not in instance:
            errors.append(f"missing required field: {field}")

    props = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        for field in instance:
            if field not in props:
                errors.append(f"unknown field: {field}")

    for field, rule in props.items():
        if field not in instance:
            continue
        val = instance[field]

        if "const" in rule and val != rule["const"]:
            errors.append(f"{field}: must equal {rule['const']!r}, got {val!r}")

        if "enum" in rule and val not in rule["enum"]:
            errors.append(f"{field}: must be one of {rule['enum']}, got {val!r}")

        types = rule.get("type")
        if types:
            if isinstance(types, str):
                types = [types]
            ok = False
            for t in types:
                if t == "string" and isinstance(val, str):
                    ok = True
                elif t == "integer" and isinstance(val, int) and not isinstance(val, bool):
                    ok = True
                elif t == "number" and isinstance(val, (int, float)) and not isinstance(val, bool):
                    ok = True
                elif t == "boolean" and isinstance(val, bool):
                    ok = True
                elif t == "object" and isinstance(val, dict):
                    ok = True
                elif t == "array" and isinstance(val, list):
                    ok = True
                elif t == "null" and val is None:
                    ok = True
            if not ok:
                errors.append(f"{field}: wrong type, expected {types}, got {type(val).__name__}")

        if isinstance(val, str):
            pat = rule.get("pattern")
            if pat and not re.match(pat, val):
                errors.append(f"{field}: does not match pattern {pat!r}")
            if rule.get("minLength") and len(val) < rule["minLength"]:
                errors.append(f"{field}: shorter than minLength {rule['minLength']}")

        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if "minimum" in rule and val < rule["minimum"]:
                errors.append(f"{field}: below minimum {rule['minimum']}")
            if "maximum" in rule and val > rule["maximum"]:
                errors.append(f"{field}: above maximum {rule['maximum']}")

        if isinstance(val, dict) and rule.get("type") == "object":
            sub_errs = validate_dict(val, rule)
            errors.extend(f"{field}.{e}" for e in sub_errs)

    return errors


def validate(instance: dict, schema_path: str) -> tuple[bool, list[str]]:
    """Load schema from path and validate. Returns (ok, errors).

    If the schema file is absent, returns (True, []) with a stderr warning rather
    than raising FileNotFoundError — callers must not hard-down on a missing schema.
    """
    import sys
    try:
        with open(schema_path) as f:
            schema = json.load(f)
    except FileNotFoundError:
        print(f"[schema_validate] WARNING: schema absent at {schema_path!r}, skipping validation", file=sys.stderr)
        return (True, [])
    errs = validate_dict(instance, schema)
    return (len(errs) == 0, errs)
