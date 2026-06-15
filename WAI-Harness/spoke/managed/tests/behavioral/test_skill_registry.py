"""
Behavioral tests for skill registry consistency.

Includes the CANARY TEST: test_no_retired_object_references
This test is expected to FAIL until Track 4 data remediation fixes WAI-Skills.jsonl.
"""

import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.wai_validate import validate_skill_entry, RETIRED_OBJECT_REFS

# Path to the REAL framework WAI-Skills.jsonl (not a test fixture)
FRAMEWORK_ROOT = Path(__file__).parent.parent.parent
REAL_SKILLS_FILE = FRAMEWORK_ROOT / "WAI-Spoke" / "skills" / "WAI-Skills.jsonl"


def _load_skills(path: Path) -> list[dict]:
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(json.loads(line))
    return entries


def test_registry_entry_validation(tmp_spoke):
    """A skill entry with all required fields validates cleanly."""
    entry = {
        "id": "test-skill",
        "name": "Test Skill",
        "type": "skill",
        "command_file": "test-skill.md",
        "objects": ["WAI-State.json"],
    }
    violations = validate_skill_entry(entry)
    assert violations == [], f"Valid entry should pass: {violations}"


def test_missing_fields_caught(tmp_spoke):
    """A skill entry missing required fields fails validation."""
    entry = {"command_file": "test.md"}
    violations = validate_skill_entry(entry)
    assert len(violations) >= 3, "Missing id, name, type should be caught"


def test_retired_object_ref_caught(tmp_spoke):
    """A skill entry referencing a retired file fails validation."""
    entry = {
        "id": "bad-skill",
        "name": "Bad Skill",
        "type": "skill",
        "command_file": "bad.md",
        "objects": ["WAI-Signals.jsonl", "WAI-State.json"],
    }
    violations = validate_skill_entry(entry)
    assert any("WAI-Signals.jsonl" in v for v in violations)


def test_consistency_registered_has_dir(tmp_spoke):
    """Every registered skill should have a matching directory."""
    wai = tmp_spoke / "WAI-Spoke"
    skills_file = wai / "skills" / "WAI-Skills.jsonl"

    # Write a skill entry
    entry = {"id": "my-skill", "name": "My Skill", "type": "skill",
             "command_file": "my-skill.md", "objects": []}
    skills_file.write_text(json.dumps(entry) + "\n")

    # Create matching dir
    (wai / "skills" / "my-skill").mkdir()
    (wai / "skills" / "my-skill" / "my-skill.md").write_text("# My Skill\n")

    violations = validate_skill_entry(entry, skills_dir=wai / "skills")
    assert violations == []


def test_consistency_missing_dir_caught(tmp_spoke):
    """A registered skill without a matching directory fails when skills_dir provided."""
    entry = {"id": "ghost-skill", "name": "Ghost", "type": "skill",
             "command_file": "ghost.md", "objects": []}
    wai = tmp_spoke / "WAI-Spoke"
    violations = validate_skill_entry(entry, skills_dir=wai / "skills")
    assert any("not found" in v for v in violations)


# ─── CANARY TEST ──────────────────────────────────────────────────────────────
# This test runs against the REAL framework WAI-Skills.jsonl.
# It is expected to FAIL until Track 4 data remediation removes retired references.


def test_no_retired_object_references():
    """
    CANARY: The real WAI-Skills.jsonl must not reference retired files.

    This test validates the framework's own data, not a test fixture.
    If it fails, WAI-Skills.jsonl has entries with objects like
    'WAI-Signals.jsonl' or 'WAI-Session-Log.jsonl' that should be removed.
    """
    if not REAL_SKILLS_FILE.exists():
        return  # Skip if not running from framework root

    entries = _load_skills(REAL_SKILLS_FILE)
    retired_refs = []
    for entry in entries:
        skill_id = entry.get("id", "?")
        for obj in entry.get("objects", []):
            if obj in RETIRED_OBJECT_REFS:
                retired_refs.append(f"{skill_id}: references '{obj}'")

    assert retired_refs == [], (
        f"WAI-Skills.jsonl has {len(retired_refs)} retired object references:\n"
        + "\n".join(f"  - {r}" for r in retired_refs)
    )
