"""
Behavioral tests for teaching discovery and adoption.

Tests teaching placement in seed/ingest/, flag detection, duplicate skip,
and prerequisite checking — using real files, no mocks.
"""

import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.wai_validate import validate_teaching


def _write_teaching(path: Path, content: str):
    path.write_text(content)


GOOD_TEACHING = """\
# Teaching: test-teaching-v1

**Type:** signal
**safe_to_auto_adopt:** true

---

## What This Teaching Does

Appends a test signal to lugs.

## Embedded Signal

```json
{"id": "test", "type": "signal", "title": "Test"}
```

## Verification Fingerprint

```bash
echo PASS
```

## Post-Completion

Move this file to processed/.
"""

TEACHING_NO_FLAG = """\
# Teaching: missing-flag-v1

**Type:** skill

---

## What This Teaching Does

Something useful.

## Verification

```bash
echo PASS
```
"""

TEACHING_NO_VERIFY = """\
# Teaching: no-verify-v1

**Type:** skill
**safe_to_auto_adopt:** false

---

## What This Teaching Does

Something without verification.
"""


def test_valid_teaching_passes(tmp_spoke):
    """A well-formed teaching passes validation."""
    violations = validate_teaching(GOOD_TEACHING)
    assert violations == [], f"Good teaching should pass: {violations}"


def test_missing_flag_caught(tmp_spoke):
    """A teaching without safe_to_auto_adopt is caught."""
    violations = validate_teaching(TEACHING_NO_FLAG)
    assert any("safe_to_auto_adopt" in v for v in violations)


def test_missing_verification_caught(tmp_spoke):
    """A teaching without a Verification section is caught."""
    violations = validate_teaching(TEACHING_NO_VERIFY)
    assert any("Verification" in v for v in violations)


def test_teaching_placed_in_ingest_discovered(tmp_spoke_with_hub):
    """A teaching placed in hub teachings_repo is discoverable via ls."""
    spoke, hub = tmp_spoke_with_hub
    teachings_dir = hub / "teachings_repo" / "framework" / "current"

    _write_teaching(teachings_dir / "test-v1.md.teaching", GOOD_TEACHING)

    # Discovery scan (mirrors wai.md Step 5)
    found = list(teachings_dir.glob("*.teaching"))
    assert len(found) == 1
    assert found[0].name == "test-v1.md.teaching"


def test_already_processed_skipped(tmp_spoke_with_hub):
    """A teaching already in processed/ is not re-adopted."""
    spoke, hub = tmp_spoke_with_hub
    teachings_dir = hub / "teachings_repo" / "framework" / "current"
    processed_dir = spoke / "WAI-Spoke" / "seed" / "ingest" / "processed"

    # Place teaching in hub
    _write_teaching(teachings_dir / "old-v1.md.teaching", GOOD_TEACHING)

    # Already processed
    _write_teaching(processed_dir / "old-v1.md.teaching", GOOD_TEACHING)

    # Discovery should find it, but adoption should skip (check processed/)
    found = list(teachings_dir.glob("*.teaching"))
    new = [f for f in found if not (processed_dir / f.name).exists()]
    assert len(new) == 0, "Already-processed teaching should be skipped"


def test_new_teaching_not_in_processed(tmp_spoke_with_hub):
    """A new teaching not in processed/ is actionable."""
    spoke, hub = tmp_spoke_with_hub
    teachings_dir = hub / "teachings_repo" / "framework" / "current"
    processed_dir = spoke / "WAI-Spoke" / "seed" / "ingest" / "processed"

    _write_teaching(teachings_dir / "new-v1.md.teaching", GOOD_TEACHING)

    found = list(teachings_dir.glob("*.teaching"))
    new = [f for f in found if not (processed_dir / f.name).exists()]
    assert len(new) == 1, "New teaching should be actionable"


def test_generate_wakeup_brief_counts_framework_teachings(tmp_spoke_with_hub, monkeypatch):
    """Wakeup brief counts pending teachings from teachings_repo/framework/current."""
    import tools.generate_wakeup_brief as wakeup_brief

    spoke, hub = tmp_spoke_with_hub
    teachings_dir = hub / "teachings_repo" / "framework" / "current"
    processed_dir = spoke / "WAI-Spoke" / "seed" / "ingest" / "processed"

    monkeypatch.setattr(wakeup_brief, "SPOKE", spoke / "WAI-Spoke")

    _write_teaching(teachings_dir / "pending-v1.md.teaching", GOOD_TEACHING)
    assert wakeup_brief.count_teachings_pending(str(hub)) == 1

    _write_teaching(processed_dir / "pending-v1.md.teaching", GOOD_TEACHING)
    assert wakeup_brief.count_teachings_pending(str(hub)) == 0


def test_flag_detection_case_insensitive(tmp_spoke):
    """Flag detection works regardless of case/format variant."""
    variants = [
        "**safe_to_auto_adopt:** true",          # canonical
        "**Safe to Auto-Adopt:** true",           # old Title Case
        "**Safe to auto-adopt:** false",          # mixed case
        "safe_to_auto_adopt: true",               # bare YAML
    ]
    import re
    for variant in variants:
        content = f"# Test\n\n{variant}\n\n## What This Teaching Does\nTest\n## Verification\nPass"
        # The wai.md Step 5 grep: case-insensitive for safe.to.auto.adopt
        match = re.search(r"safe.to.auto.adopt", content, re.IGNORECASE)
        assert match is not None, f"Failed to detect flag in: {variant}"
