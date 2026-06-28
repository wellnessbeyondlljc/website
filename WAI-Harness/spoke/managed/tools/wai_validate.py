#!/usr/bin/env python3
"""
WAI Validation Library — Single Source of Truth

Pure-function validators for every canonical WAI structure.
Used by: spoke_health_check.py, behavioral tests, e2e tests, pre-commit hook.

All schema knowledge lives HERE. Nothing else should duplicate type catalogs,
required field lists, or structural rules.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _spoke_base(spoke_path) -> Path:
    """The spoke working base holding lugs/, base-aware. On a v4 spoke this
    resolves to WAI-Harness/spoke/local; PRE-FIX validators blindly appended
    'WAI-Spoke' so they checked a nonexistent tree and always reported it
    missing on a v4 spoke (impl-fix-p2-v3noop-sweep-v1). A path already pointing
    at the base (name 'WAI-Spoke' or 'local') is used as-is."""
    p = Path(spoke_path)
    if p.name in ("WAI-Spoke", "local"):
        return p
    try:
        from wai_paths import resolve_wai_root
        base, mode = resolve_wai_root(str(p))
        if base and mode != "none":
            return Path(base)
    except Exception:
        pass
    return p / "WAI-Spoke"  # last-resort v3 fallback


# ─── Canonical Catalogs ──────────────────────────────────────────────────────

VALID_LUG_TYPES: Set[str] = {
    # Promoted types (have dedicated bytype/ folders)
    "epic",
    "task",
    "feature",
    "bug",
    "implementation",
    "signal",
    "session-summary",
    "chain",
    # Rare types (go to bytype/other/)
    "idea",
    "policy",
    "observation",
    "learning",
    "maintenance",
    "decision",
    "protocol",
    "diagnosis",
    "refactor",
    "review",
    "foundation",
    "core-protocol",
    "config",
    "response",
    # Operational types
    "autosave",
    "delivery_confirmation",
    "phone-home",
    "session",
    "shipit",
    "lug",
}

VALID_LUG_STATUSES: Set[str] = {
    # Short forms
    "o",  # open
    "p",  # in_progress
    "c",  # completed
    "b",  # blocked
    # Long forms
    "open",
    "in_progress",
    "in-progress",
    "completed",
    "closed",
    "resolved",
    "blocked",
    "published",
    "reviewed",
    "proposed",
    "archived",
    # Signal-specific
    "undelivered",
    "delivered",
    # Chain-specific
    "claimed",
    "deferred",
}

# Types that REQUIRE PEV fields (perceive, execute, verify)
PEV_REQUIRED_TYPES: Set[str] = {
    "task",
    "epic",
    "bug",
    "feature",
    "review",
    "implementation",
}

# Required fields for all lugs: (short_key, long_key)
REQUIRED_LUG_FIELDS = [
    ("i", "id"),
    ("ty", "type"),
]

# Status field keys
STATUS_KEYS = ("s", "status")

# Title field keys — required for non-closed/non-reconciled lugs
TITLE_KEYS = ("t", "title")

# Retired files that should NOT exist in a canonical spoke
RETIRED_FILES = [
    "WAI-Signals.jsonl",
    "WAI-Session-Log.jsonl",
]

RETIRED_LUG_DIRS = [
    "lugs/inbox",
    "lugs/outbox",
]

# Retired object references that should NOT appear in WAI-Skills.jsonl objects arrays
RETIRED_OBJECT_REFS = {
    "WAI-Signals.jsonl",
    "WAI-Session-Log.jsonl",
}

# Required bytype subdirectories
REQUIRED_BYTYPE_DIRS = {
    "epic": ["open", "in_progress", "completed"],
    "task": ["open", "in_progress", "completed"],
    "feature": ["open", "in_progress", "completed"],
    "bug": ["open", "in_progress", "completed"],
    "implementation": ["in_progress", "completed"],
    "signal": ["undelivered", "delivered"],
    "session-summary": [],  # no status subfolder
    "chain": ["open", "in_progress", "completed"],
    "other": ["open", "completed"],
}

# Required operational folders under lugs/
REQUIRED_LUG_OPERATIONAL_DIRS = ["incoming", "outgoing", "reference"]


# ─── Validators ──────────────────────────────────────────────────────────────


def _get(d: dict, *keys) -> Any:
    """Get value from dict trying multiple keys (short/long form support)."""
    for k in keys:
        if k in d:
            return d[k]
    return None


def validate_lug(lug: dict, check_pev: bool = True) -> List[str]:
    """
    Validate a lug dictionary against the canonical schema.

    Returns list of violation strings. Empty list = valid.
    """
    violations = []

    # Required fields: id, type
    lug_id = _get(lug, "i", "id")
    if lug_id is None:
        violations.append("Missing required field: 'i' or 'id'")

    lug_type = _get(lug, "ty", "type")
    if lug_type is None:
        violations.append("Missing required field: 'ty' or 'type'")
    elif lug_type not in VALID_LUG_TYPES:
        violations.append(f"Invalid type '{lug_type}' — not in canonical catalog")

    # Status validation
    status = _get(lug, "s", "status")
    if status and status not in VALID_LUG_STATUSES:
        violations.append(f"Invalid status '{status}' — not in canonical catalog")

    # Title — required for non-closed/non-reconciled lugs
    is_closed = status in ("c", "closed", "resolved", "published", "reviewed", "completed", "archived", "delivered")
    is_reconciled = lug.get("reconciled", False)
    title = _get(lug, "t", "title")
    if not title and not is_closed and not is_reconciled:
        violations.append("Missing required field: 't' or 'title' (required for non-closed lugs)")

    # created_at
    created_at = _get(lug, "ca", "created_at")
    if created_at is None:
        violations.append("Missing required field: 'ca' or 'created_at'")

    # PEV enforcement for actionable types
    if check_pev and lug_type in PEV_REQUIRED_TYPES and not is_closed:
        for field in ("perceive", "execute", "verify"):
            val = lug.get(field)
            if val is None:
                violations.append(f"Missing PEV field: '{field}' (required for type '{lug_type}')")
            elif isinstance(val, str) and len(val.strip()) < 10:
                violations.append(f"PEV field '{field}' is too vague (< 10 chars): '{val}'")

    # routed_to — should be present (default LOCAL)
    if "routed_to" not in lug and lug_type not in ("autosave", "session-summary", "delivery_confirmation", "phone-home"):
        violations.append("Missing 'routed_to' field (should be LOCAL, FRAMEWORK, or SIGNAL)")
    elif "routed_to" in lug and lug["routed_to"] not in ("LOCAL", "FRAMEWORK", "SIGNAL"):
        violations.append(f"Invalid routed_to value: '{lug['routed_to']}' — must be LOCAL, FRAMEWORK, or SIGNAL")

    # Cross-spoke lugs need _behavior_directive
    if lug.get("routed_to") in ("FRAMEWORK", "SIGNAL"):
        if "_behavior_directive" not in lug:
            violations.append("Cross-spoke lug missing '_behavior_directive' block")

    return violations


def validate_wai_state(state: dict) -> List[str]:
    """
    Validate WAI-State.json structure.

    Returns list of violation strings. Empty list = valid.
    """
    violations = []

    # Required top-level keys
    for key in ("wheel", "_session_state"):
        if key not in state:
            violations.append(f"Missing required top-level key: '{key}'")

    wheel = state.get("wheel", {})
    session = state.get("_session_state", {})

    # wheel section
    for key in ("name", "version"):
        if key not in wheel:
            violations.append(f"Missing wheel.{key}")

    # Version format (semver-like)
    version = wheel.get("version", "")
    if version and not re.match(r"^\d+\.\d+\.\d+", version):
        violations.append(f"wheel.version '{version}' is not semver format (expected X.Y.Z)")

    # node_type
    if "node_type" not in wheel:
        violations.append("Missing wheel.node_type")
    elif wheel["node_type"] not in ("spoke", "hub"):
        violations.append(f"Invalid wheel.node_type: '{wheel['node_type']}'")

    # hub_path — warn if missing (not a hard fail for spokes that haven't connected)
    if wheel.get("hub_path") is None:
        violations.append("WARNING: wheel.hub_path is null — hub connectivity unavailable")

    # framework_version
    if "framework_version" not in wheel:
        violations.append("Missing wheel.framework_version")

    # _session_state section
    # Note: protocol_completed moved to WAI-Spoke/runtime/session-guard.json (not in WAI-State.json)

    if "session_count" not in session:
        violations.append("Missing _session_state.session_count")
    elif not isinstance(session.get("session_count"), int):
        violations.append(f"_session_state.session_count must be int, got {type(session.get('session_count')).__name__}")

    if "last_closeout" not in session:
        violations.append("Missing _session_state.last_closeout")

    return violations


def validate_teaching(content: str) -> List[str]:
    """
    Validate a teaching file's text content against the canonical template.

    Returns list of violation strings. Empty list = valid.
    """
    violations = []

    # safe_to_auto_adopt flag MUST be present (resolves contradictory-defaults issue)
    if not re.search(r"safe_to_auto_adopt", content, re.IGNORECASE):
        violations.append("Missing safe_to_auto_adopt flag — MUST be present in every teaching")

    # Verification section
    if "## Verification" not in content and "Verification Fingerprint" not in content:
        violations.append("Missing ## Verification or Verification Fingerprint section")

    # Apply Instructions or embedded action
    has_apply = any(phrase in content for phrase in [
        "## Apply Instructions",
        "## How to Apply",
        "## What This Teaching Does",
        "## Embedded Signal",
    ])
    if not has_apply:
        violations.append("Missing apply instructions section (## Apply Instructions, ## How to Apply, or ## What This Teaching Does)")

    return violations


def validate_skill_entry(
    entry: dict,
    skills_dir: Optional[Path] = None,
) -> List[str]:
    """
    Validate a WAI-Skills.jsonl entry.

    Args:
        entry: Parsed JSONL line
        skills_dir: If provided, verify command_file exists on disk

    Returns list of violation strings. Empty list = valid.
    """
    violations = []

    # Required fields
    for field in ("id", "name", "type"):
        if field not in entry:
            violations.append(f"Missing required field: '{field}'")

    # command_file
    if "command_file" not in entry:
        violations.append("Missing 'command_file' field")

    # objects array — no retired file references
    objects = entry.get("objects", [])
    for obj in objects:
        if obj in RETIRED_OBJECT_REFS:
            violations.append(f"Objects array references retired file: '{obj}'")

    # Verify command_file exists on disk (if skills_dir provided)
    if skills_dir and "command_file" in entry:
        skill_id = entry.get("id", "")
        cmd_file = entry["command_file"]
        # Skills can be in skills/{id}/{cmd_file} or templates/commands/{cmd_file}
        # Check skills dir first
        skill_path = skills_dir / skill_id / cmd_file
        if not skill_path.exists():
            violations.append(f"command_file '{cmd_file}' not found at {skill_path}")

    return violations


def validate_bytype_structure(spoke_path) -> List[str]:
    """
    Validate the bytype/ directory hierarchy is complete.

    Args:
        spoke_path: Path to the WAI-Spoke/ directory (or parent containing WAI-Spoke/).
                    Accepts str or Path.

    Returns list of violation strings. Empty list = valid.
    """
    violations = []
    spoke_path = Path(spoke_path)

    # Resolve the spoke working base (v4: WAI-Harness/spoke/local; v3: WAI-Spoke)
    wai_spoke = _spoke_base(spoke_path)

    if not wai_spoke.exists():
        violations.append(f"spoke working base not found at {wai_spoke}")
        return violations

    lugs_dir = wai_spoke / "lugs"
    if not lugs_dir.exists():
        violations.append("WAI-Spoke/lugs/ directory missing")
        return violations

    # Check bytype hierarchy
    bytype_dir = lugs_dir / "bytype"
    if not bytype_dir.exists():
        violations.append("WAI-Spoke/lugs/bytype/ directory missing")
        return violations

    for type_name, status_dirs in REQUIRED_BYTYPE_DIRS.items():
        type_dir = bytype_dir / type_name
        if not type_dir.exists():
            violations.append(f"Missing bytype directory: bytype/{type_name}/")
            continue
        for status in status_dirs:
            status_dir = type_dir / status
            if not status_dir.exists():
                violations.append(f"Missing bytype subdirectory: bytype/{type_name}/{status}/")

    # Check operational folders
    for op_dir in REQUIRED_LUG_OPERATIONAL_DIRS:
        if not (lugs_dir / op_dir).exists():
            violations.append(f"Missing operational directory: lugs/{op_dir}/")

    for retired_dir in RETIRED_LUG_DIRS:
        if (wai_spoke / retired_dir).exists():
            violations.append(f"Retired legacy directory still exists: WAI-Spoke/{retired_dir}/")

    # Check for retired files
    for retired in RETIRED_FILES:
        retired_path = wai_spoke / retired
        if retired_path.exists():
            violations.append(f"Retired file still exists: {retired}")

    # Check other required spoke directories
    for required_dir in ("sessions", "skills", "seed/ingest", "seed/ingest/processed"):
        if not (wai_spoke / required_dir).exists():
            violations.append(f"Missing required directory: WAI-Spoke/{required_dir}/")

    return violations


def validate_lug_file_location(
    lug: dict,
    file_path: Path,
) -> List[str]:
    """
    Validate that a lug file is in the correct bytype/ location for its type and status.

    Args:
        lug: Parsed lug dict
        file_path: Actual path of the .json file

    Returns list of violation strings. Empty list = valid.
    """
    violations = []

    lug_type = _get(lug, "ty", "type")
    status = _get(lug, "s", "status")

    if not lug_type or not file_path:
        return violations

    # Map status to expected directory
    status_to_dir = {
        "o": "open", "open": "open",
        "p": "in_progress", "in_progress": "in_progress", "in-progress": "in_progress",
        "c": "completed", "completed": "completed", "closed": "completed",
        "resolved": "completed", "archived": "completed",
        "b": "open", "blocked": "open",  # blocked lugs stay in open
        "undelivered": "undelivered", "delivered": "delivered",
    }

    # Determine expected type folder
    promoted_types = {"epic", "task", "feature", "bug", "implementation", "signal", "session-summary", "chain"}
    expected_type_dir = lug_type if lug_type in promoted_types else "other"

    # Check type directory
    parts = file_path.parts
    if "bytype" in parts:
        bytype_idx = parts.index("bytype")
        if len(parts) > bytype_idx + 1:
            actual_type_dir = parts[bytype_idx + 1]
            if actual_type_dir != expected_type_dir:
                violations.append(
                    f"Lug type '{lug_type}' is in bytype/{actual_type_dir}/ "
                    f"but should be in bytype/{expected_type_dir}/"
                )

        # Check status directory
        if status and len(parts) > bytype_idx + 2:
            actual_status_dir = parts[bytype_idx + 2]
            expected_status_dir = status_to_dir.get(status)
            if expected_status_dir and actual_status_dir != expected_status_dir:
                violations.append(
                    f"Lug status '{status}' is in {actual_status_dir}/ "
                    f"but should be in {expected_status_dir}/"
                )

    return violations


# ─── Convenience ─────────────────────────────────────────────────────────────


def validate_all_active_lugs(spoke_path) -> Dict[str, List[str]]:
    """
    Validate all active lugs (open/in_progress/undelivered) in a spoke.

    Returns dict of {lug_file_path: [violations]}.
    """
    results = {}
    spoke_path = _spoke_base(spoke_path)

    bytype = spoke_path / "lugs" / "bytype"
    if not bytype.exists():
        return {"bytype/": ["bytype/ directory not found"]}

    for json_file in bytype.rglob("*.json"):
        # Only check active lugs
        parent = json_file.parent.name
        if parent not in ("open", "in_progress", "undelivered"):
            continue

        try:
            lug = json.loads(json_file.read_text())
        except json.JSONDecodeError as e:
            results[str(json_file)] = [f"Invalid JSON: {e}"]
            continue

        violations = validate_lug(lug)
        violations.extend(validate_lug_file_location(lug, json_file))

        if violations:
            results[str(json_file)] = violations

    return results
