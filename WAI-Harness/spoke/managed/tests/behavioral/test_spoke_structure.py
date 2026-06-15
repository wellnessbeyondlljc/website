"""
Behavioral tests for spoke directory structure validation.

Creates real spokes, validates structure, introduces drift, verifies detection.
"""

import json
import shutil
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.wai_validate import validate_bytype_structure, validate_wai_state


def test_canonical_spoke_passes(tmp_spoke):
    """A spoke created by the fixture passes all structure checks."""
    violations = validate_bytype_structure(tmp_spoke)
    assert violations == [], f"Canonical spoke should pass: {violations}"


def test_missing_bytype_dir_caught(tmp_spoke):
    """Removing a bytype subdirectory is caught."""
    shutil.rmtree(tmp_spoke / "WAI-Spoke/lugs/bytype/signal")
    violations = validate_bytype_structure(tmp_spoke)
    signal_violations = [v for v in violations if "signal" in v]
    assert len(signal_violations) >= 1, "Missing signal/ dir should be caught"


def test_legacy_inbox_dir_caught(tmp_spoke):
    """Legacy inbox/ directory is rejected after incoming/outgoing migration."""
    (tmp_spoke / "WAI-Spoke/lugs/inbox").mkdir()
    violations = validate_bytype_structure(tmp_spoke)
    assert any("lugs/inbox" in v for v in violations)


def test_retired_file_caught(tmp_spoke):
    """A retired file like WAI-Signals.jsonl is caught."""
    retired = tmp_spoke / "WAI-Spoke" / "WAI-Signals.jsonl"
    retired.write_text("# should not exist\n")
    violations = validate_bytype_structure(tmp_spoke)
    assert any("WAI-Signals.jsonl" in v for v in violations), "Retired file should be caught"


def test_missing_sessions_caught(tmp_spoke):
    """Missing sessions/ directory is caught."""
    shutil.rmtree(tmp_spoke / "WAI-Spoke/sessions")
    violations = validate_bytype_structure(tmp_spoke)
    assert any("sessions" in v for v in violations)


def test_missing_skills_caught(tmp_spoke):
    """Missing skills/ directory is caught."""
    shutil.rmtree(tmp_spoke / "WAI-Spoke/skills")
    violations = validate_bytype_structure(tmp_spoke)
    assert any("skills" in v for v in violations)


def test_valid_wai_state(tmp_spoke):
    """A well-formed WAI-State.json passes validation."""
    state = json.loads((tmp_spoke / "WAI-Spoke/WAI-State.json").read_text())
    violations = validate_wai_state(state)
    # Only warnings expected (hub_path is null in fixture)
    errors = [v for v in violations if not v.startswith("WARNING")]
    assert errors == [], f"Valid state should have no errors: {errors}"


def test_invalid_wai_state_caught(tmp_spoke):
    """A WAI-State.json missing required fields is caught."""
    state = {"wheel": {"name": "test"}}  # Missing version, _session_state
    violations = validate_wai_state(state)
    assert len(violations) >= 3, f"Expected multiple violations: {violations}"


def test_non_semver_version_caught(tmp_spoke):
    """A non-semver version string is caught."""
    state = json.loads((tmp_spoke / "WAI-Spoke/WAI-State.json").read_text())
    state["wheel"]["version"] = "dev"
    violations = validate_wai_state(state)
    assert any("semver" in v for v in violations)


def test_non_int_session_count_caught(tmp_spoke):
    """A non-integer session_count is caught."""
    state = json.loads((tmp_spoke / "WAI-Spoke/WAI-State.json").read_text())
    state["_session_state"]["session_count"] = "five"
    violations = validate_wai_state(state)
    assert any("session_count" in v for v in violations)
