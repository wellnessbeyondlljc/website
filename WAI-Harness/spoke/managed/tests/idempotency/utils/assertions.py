#!/usr/bin/env python3
"""
Custom Assertions for WAI Idempotency Tests

Specialized assertion functions for validating WAI state consistency,
file integrity, and idempotent operation outcomes.

Updated for canonical bytype/ storage:
- Lugs stored as individual JSON files in lugs/bytype/{type}/{status}/{id}.json
- Signals in lugs/bytype/signal/{undelivered,delivered}/
- WAI-Lugs.jsonl and WAI-Signals.jsonl are RETIRED
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Set, Optional


def assert_wai_state_valid(state: Dict[str, Any], context: str = ""):
    """
    Assert that a WAI-State.json structure is valid.

    Args:
        state: Parsed WAI-State.json content
        context: Context for error messages
    """
    required_keys = ["wheel", "_session_state"]
    for key in required_keys:
        assert key in state, f"{context}: Missing required key '{key}' in WAI-State"

    # Validate wheel section
    wheel = state["wheel"]
    wheel_required = ["name", "version", "framework_version"]
    for key in wheel_required:
        assert key in wheel, f"{context}: Missing required wheel key '{key}'"

    # Validate session state
    session_state = state["_session_state"]
    session_required = ["session_count", "protocol_completed"]
    for key in session_required:
        assert key in session_state, (
            f"{context}: Missing required session_state key '{key}'"
        )

    assert isinstance(session_state["session_count"], int), (
        f"{context}: session_count must be integer"
    )
    assert isinstance(session_state["protocol_completed"], bool), (
        f"{context}: protocol_completed must be boolean"
    )


def assert_lugs_valid(lugs: List[Dict[str, Any]], context: str = ""):
    """
    Assert that a list of lugs are valid according to schema.

    Args:
        lugs: List of lug dictionaries
        context: Context for error messages
    """
    required_fields = ["i", "ty", "s", "ca"]
    valid_types = {
        "task",
        "bug",
        "feature",
        "epic",
        "decision",
        "signal",
        "autosave",
        "session-summary",
        "review",
        "policy",
    }
    valid_statuses = {
        "o",
        "p",
        "c",
        "open",
        "in-progress",
        "closed",
        "completed",
        "archived",
    }

    for i, lug in enumerate(lugs):
        lug_context = f"{context} lug {i + 1} (id={lug.get('i', '?')})"

        # Check required fields (except title which is optional for closed/reconciled)
        for field in required_fields:
            if field == "t" and (lug.get("s") == "c" or lug.get("reconciled")):
                continue  # Title optional for closed/reconciled lugs
            assert field in lug, f"{lug_context}: Missing required field '{field}'"

        # Validate type
        lug_type = lug.get("ty", "")
        assert lug_type in valid_types, (
            f"{lug_context}: Invalid type '{lug_type}', must be one of {valid_types}"
        )

        # Validate status
        status = lug.get("s", "")
        assert status in valid_statuses, (
            f"{lug_context}: Invalid status '{status}', must be one of {valid_statuses}"
        )


def compare_states(
    state1: Dict[str, Any],
    state2: Dict[str, Any],
    ignore_keys: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Compare two WAI states and return differences.

    Args:
        state1: First state
        state2: Second state
        ignore_keys: Keys to ignore in comparison

    Returns:
        Dictionary describing differences
    """
    if ignore_keys is None:
        ignore_keys = {"_session_state.last_modified_at", "wheel.last_modified"}

    def deep_diff(obj1, obj2, path=""):
        differences = {}

        if isinstance(obj1, dict) and isinstance(obj2, dict):
            all_keys = set(obj1.keys()) | set(obj2.keys())
            for key in all_keys:
                key_path = f"{path}.{key}" if path else key

                if key_path in ignore_keys:
                    continue

                if key not in obj1:
                    differences[key_path] = {"added": obj2[key]}
                elif key not in obj2:
                    differences[key_path] = {"removed": obj1[key]}
                elif obj1[key] != obj2[key]:
                    if isinstance(obj1[key], dict) and isinstance(obj2[key], dict):
                        nested_diff = deep_diff(obj1[key], obj2[key], key_path)
                        differences.update(nested_diff)
                    else:
                        differences[key_path] = {
                            "changed_from": obj1[key],
                            "changed_to": obj2[key],
                        }
        else:
            if obj1 != obj2:
                differences[path] = {"changed_from": obj1, "changed_to": obj2}

        return differences

    return deep_diff(state1, state2)


def assert_no_file_corruption(state: Dict[str, Any], context: str = ""):
    """
    Assert that a WAI state shows no signs of file corruption.

    Args:
        state: WAI-State.json content
        context: Context for error messages
    """
    # Basic structure validation
    assert_wai_state_valid(state, context)

    # Check for corruption indicators
    session_state = state["_session_state"]

    # Session count should be non-negative
    assert session_state["session_count"] >= 0, (
        f"{context}: session_count cannot be negative"
    )

    # Timestamps should be properly formatted if present
    for ts_field in ["last_modified_at", "last_closeout"]:
        if ts_field in session_state and session_state[ts_field]:
            ts_value = session_state[ts_field]
            assert isinstance(ts_value, str), f"{context}: {ts_field} should be string"
            # Basic ISO format check (simplified)
            assert "T" in ts_value and ("Z" in ts_value or "+" in ts_value), (
                f"{context}: {ts_field} should be ISO-8601 format"
            )


def assert_single_winner(results: List[Dict[str, Any]], context: str = ""):
    """
    Assert that exactly one operation succeeded in concurrent scenario.

    Args:
        results: List of operation results
        context: Context for error messages
    """
    successes = [r for r in results if r.get("success", False)]
    failures = [r for r in results if not r.get("success", True)]

    assert len(successes) == 1, (
        f"{context}: Expected exactly 1 success, got {len(successes)}"
    )
    assert len(failures) == len(results) - 1, (
        f"{context}: Expected {len(results) - 1} failures, got {len(failures)}"
    )


def assert_no_duplicate_signals(signals: List[Dict[str, Any]], context: str = ""):
    """
    Assert that signals list contains no duplicates.

    Checks both by timestamp (ca field, with fallback to legacy timestamp field)
    and by content (t field, with fallback to legacy signal field).

    Args:
        signals: List of signal dictionaries
        context: Context for error messages
    """
    seen_timestamps = set()
    seen_content = set()

    for i, signal in enumerate(signals):
        signal_context = f"{context} signal {i + 1}"

        # Check timestamp uniqueness — use ca (canonical) with fallback to timestamp (legacy)
        timestamp = signal.get("ca", signal.get("timestamp", ""))
        assert timestamp not in seen_timestamps, (
            f"{signal_context}: Duplicate timestamp '{timestamp}'"
        )
        seen_timestamps.add(timestamp)

        # Check content uniqueness — use t (canonical) with fallback to signal (legacy)
        content = signal.get("t", signal.get("signal", ""))
        content_hash = hashlib.md5(content.encode()).hexdigest()
        assert content_hash not in seen_content, (
            f"{signal_context}: Duplicate signal content"
        )
        seen_content.add(content_hash)


def assert_teaching_files_unique(teaching_files: List[Path], context: str = ""):
    """
    Assert that teaching files have unique content.

    Args:
        teaching_files: List of teaching file paths
        context: Context for error messages
    """
    content_hashes = set()

    for teaching_file in teaching_files:
        if not teaching_file.exists():
            continue

        content = teaching_file.read_text()
        content_hash = hashlib.md5(content.encode()).hexdigest()

        assert content_hash not in content_hashes, (
            f"{context}: Duplicate teaching content in {teaching_file.name}"
        )
        content_hashes.add(content_hash)


def assert_migration_state_valid(
    state: Dict[str, Any], expected_version: str, context: str = ""
):
    """
    Assert that migration resulted in valid state with correct version.

    Args:
        state: WAI-State.json content after migration
        expected_version: Expected framework version
        context: Context for error messages
    """
    assert_wai_state_valid(state, context)

    actual_version = state["wheel"].get("framework_version", "")
    assert actual_version == expected_version, (
        f"{context}: Expected framework version '{expected_version}', got '{actual_version}'"
    )


def assert_no_partial_updates(state: Dict[str, Any], context: str = ""):
    """
    Assert that state shows no signs of partial updates (atomic operation).

    Args:
        state: WAI-State.json content
        context: Context for error messages
    """
    assert_wai_state_valid(state, context)

    # Check internal consistency
    session_state = state["_session_state"]

    # If last_closeout is set, session_count should be > 0
    if session_state.get("last_closeout"):
        assert session_state["session_count"] > 0, (
            f"{context}: Inconsistent state - has closeout but session_count is 0"
        )

    # If protocol_completed is True, should have valid session metadata
    if session_state["protocol_completed"]:
        assert session_state.get("last_modified_by"), (
            f"{context}: protocol_completed=True but no last_modified_by"
        )


def assert_idempotent_outcome(
    first_result: Dict[str, Any], second_result: Dict[str, Any], context: str = ""
):
    """
    Assert that second operation detected completion and produced idempotent outcome.

    Args:
        first_result: Result of first operation
        second_result: Result of second operation
        context: Context for error messages
    """
    assert first_result.get("success", False), (
        f"{context}: First operation should succeed"
    )
    assert second_result.get("success", False), (
        f"{context}: Second operation should succeed (idempotent)"
    )

    # Second operation should indicate it was skipped or detected completion
    assert (
        second_result.get("skipped", False)
        or second_result.get("already_completed", False)
        or "already" in second_result.get("message", "").lower()
    ), f"{context}: Second operation should indicate completion was detected"


def assert_file_not_corrupted(file_path: Path, context: str = ""):
    """
    Assert that a JSON file is not corrupted (can be parsed).

    Args:
        file_path: Path to JSON file
        context: Context for error messages
    """
    assert file_path.exists(), f"{context}: File {file_path} does not exist"

    try:
        with open(file_path) as f:
            json.load(f)
    except json.JSONDecodeError as e:
        raise AssertionError(f"{context}: File {file_path} is corrupted: {e}")
    except Exception as e:
        raise AssertionError(f"{context}: Cannot read file {file_path}: {e}")


def assert_bytype_integrity(wai_spoke: Path, context: str = ""):
    """
    Assert that bytype/ directory structure has valid lug files.

    Scans all .json files under lugs/bytype/ and validates each one
    is parseable JSON with required lug fields.

    Args:
        wai_spoke: Path to WAI-Spoke directory
        context: Context for error messages
    """
    bytype_dir = wai_spoke / "lugs" / "bytype"
    assert bytype_dir.exists(), f"{context}: bytype/ directory does not exist at {bytype_dir}"

    lugs = []
    for json_file in bytype_dir.rglob("*.json"):
        try:
            with open(json_file) as f:
                lug = json.load(f)
                lugs.append(lug)
        except json.JSONDecodeError as e:
            raise AssertionError(
                f"{context}: Invalid JSON in {json_file}: {e}"
            )
        except Exception as e:
            raise AssertionError(f"{context}: Cannot read {json_file}: {e}")

    # Validate lug structure
    if lugs:
        assert_lugs_valid(lugs, f"{context} bytype")


def assert_signal_files_integrity(wai_spoke: Path, context: str = ""):
    """
    Assert that signal files in bytype/signal/ are valid.

    Checks both undelivered/ and delivered/ subdirectories.

    Args:
        wai_spoke: Path to WAI-Spoke directory
        context: Context for error messages
    """
    signal_dir = wai_spoke / "lugs" / "bytype" / "signal"
    if not signal_dir.exists():
        return  # No signals is valid

    for subdir in ["undelivered", "delivered"]:
        status_dir = signal_dir / subdir
        if not status_dir.exists():
            continue
        for json_file in status_dir.glob("*.json"):
            try:
                with open(json_file) as f:
                    lug = json.load(f)
                assert lug.get("ty") == "signal", (
                    f"{context}: File {json_file.name} in signal/{subdir}/ has type "
                    f"'{lug.get('ty')}', expected 'signal'"
                )
            except json.JSONDecodeError as e:
                raise AssertionError(
                    f"{context}: Invalid JSON in {json_file}: {e}"
                )


def assert_lugs_file_integrity(lugs_file: Path, context: str = ""):
    """
    Assert that WAI-Lugs.jsonl file has valid structure.

    NOTE: WAI-Lugs.jsonl is RETIRED. This function is kept for backward
    compatibility but now also accepts the retired marker format. For new
    tests, prefer assert_bytype_integrity().

    Args:
        lugs_file: Path to lugs file
        context: Context for error messages
    """
    assert lugs_file.exists(), f"{context}: Lugs file {lugs_file} does not exist"

    lugs = []
    line_num = 0

    try:
        with open(lugs_file) as f:
            for line in f:
                line_num += 1
                line = line.strip()
                if not line or line.startswith("#"):
                    continue  # Skip empty lines and comment markers

                lug = json.loads(line)
                lugs.append(lug)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"{context}: Invalid JSON in {lugs_file} at line {line_num}: {e}"
        )
    except Exception as e:
        raise AssertionError(f"{context}: Cannot read {lugs_file}: {e}")

    # Validate lug structure (if any actual lugs exist, not just retired marker)
    if lugs:
        assert_lugs_valid(lugs, f"{context} lugs file")


def assert_git_state_clean(repo_dir: Path, context: str = ""):
    """
    Assert that git repository is in clean state.

    Args:
        repo_dir: Repository directory
        context: Context for error messages
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        assert result.stdout.strip() == "", (
            f"{context}: Git repository has uncommitted changes:\n{result.stdout}"
        )

    except subprocess.CalledProcessError as e:
        raise AssertionError(f"{context}: Git status check failed: {e}")
    except FileNotFoundError:
        # Git not available, skip check
        pass


def assert_operation_logged(
    log_entries: List[Dict[str, Any]], operation: str, context: str = ""
):
    """
    Assert that a specific operation was logged.

    Args:
        log_entries: List of log entries
        operation: Operation name to find
        context: Context for error messages
    """
    matching_entries = [
        entry for entry in log_entries if operation in entry.get("action", "").lower()
    ]

    assert len(matching_entries) > 0, (
        f"{context}: Operation '{operation}' not found in log entries"
    )


# Test result validation helpers


def validate_closeout_result(result: Dict[str, Any]) -> List[str]:
    """
    Validate closeout operation result structure.

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    if "success" not in result:
        errors.append("Missing 'success' field")

    if result.get("success"):
        # Successful closeout should have certain fields
        if "session_summary" not in result:
            errors.append("Successful closeout missing session_summary")
    else:
        # Failed closeout should have error
        if "error" not in result:
            errors.append("Failed closeout missing error message")

    return errors


def validate_migration_result(result: Dict[str, Any]) -> List[str]:
    """
    Validate migration operation result structure.

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    if "success" not in result:
        errors.append("Missing 'success' field")

    if "target_version" not in result:
        errors.append("Missing target_version field")

    if result.get("success") and not result.get("skipped"):
        if "files_copied" not in result:
            errors.append("Successful migration missing files_copied")

    return errors


# Debugging helpers


def dump_state_diff(state1: Dict[str, Any], state2: Dict[str, Any]) -> str:
    """
    Generate human-readable diff of two states for debugging.

    Args:
        state1: First state
        state2: Second state

    Returns:
        Formatted diff string
    """
    differences = compare_states(state1, state2)

    if not differences:
        return "States are identical"

    lines = ["State differences:"]
    for path, change in differences.items():
        if "added" in change:
            lines.append(f"  + {path}: {change['added']}")
        elif "removed" in change:
            lines.append(f"  - {path}: {change['removed']}")
        elif "changed_from" in change:
            lines.append(
                f"  ~ {path}: {change['changed_from']} -> {change['changed_to']}"
            )

    return "\n".join(lines)
