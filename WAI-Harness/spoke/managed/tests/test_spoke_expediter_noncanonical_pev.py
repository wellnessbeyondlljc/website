"""test_spoke_expediter_noncanonical_pev.py

Verifies that score_lug_quality() reads non-canonical scope keys before flagging
'missing PEV'. Producers such as external_api_integration and architecture_oversight
store scope under: issue, summary, description, a nested pev object, and
files_to_modify/files_to_create/file_targets instead of target_files.

AC from impl-expediter-read-noncanonical-pev-keys-v1:
  - A lug with content only under {issue, summary, files_to_modify, nested pev}
    must score full PEV (perceive+execute+verify all pass) and produce ZERO
    missing_fields entries for perceive/execute/verify.
  - needs_you_note and sibling informational types must be excluded from scan_lugs()
    so they never reach the PEV gate.
"""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import spoke_expediter  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _noncanonical_lug():
    """Lug with scope stored entirely under non-canonical keys (issue, summary,
    files_to_modify, and a nested pev object). Simulates external_api_integration
    / architecture-oversight producer output."""
    return {
        "id": "test-noncanonical-001",
        "type": "implementation",
        "status": "open",
        "title": "Non-canonical scope lug",
        # Non-canonical perceive
        "issue": "Read WAI-Harness/spoke/managed/tools/spoke_expediter.py score_lug_quality() to understand current PEV gate logic and which keys are checked.",
        # Non-canonical execute (nested pev)
        "pev": {
            "execute": "1. Open spoke_expediter.py. 2. Locate score_lug_quality() around line 90. 3. Add ordered fallbacks for perceive/execute/verify keys. 4. Add fallbacks for target_files (files_to_modify, files_to_create, file_targets). 5. Run existing tests to confirm no regressions.",
            "verify": "Run pytest tests/test_spoke_expediter_noncanonical_pev.py — all assertions pass. Run existing tests — no regressions.",
        },
        # Non-canonical target_files
        "files_to_modify": ["WAI-Harness/spoke/managed/tools/spoke_expediter.py"],
        "acceptance_criteria": [
            "score_lug_quality reads non-canonical keys",
            "no false-positive missing-PEV findings for scope-complete lugs",
        ],
        "model_fit": "haiku",
    }


def _noncanonical_lug_summary_description():
    """Variant using summary/description rather than issue."""
    return {
        "id": "test-noncanonical-002",
        "type": "implementation",
        "status": "open",
        "title": "Non-canonical via summary/description",
        "summary": "Read WAI-Harness/spoke/managed/tools/spoke_expediter.py and understand the score_lug_quality function before making any changes.",
        "execute": "1. Locate score_lug_quality in spoke_expediter.py. 2. Add fallback chains. 3. Verify tests pass.",
        "verify": "pytest confirms all tests green; no regressions in existing suite.",
        "acceptance_criteria": ["all non-canonical keys recognized"],
        "file_targets": ["WAI-Harness/spoke/managed/tools/spoke_expediter.py"],
        "model_fit": "sonnet",
    }


def _noncanonical_lug_files_to_create():
    """Variant using files_to_create for target_files."""
    return {
        "id": "test-noncanonical-003",
        "type": "implementation",
        "status": "open",
        "title": "Non-canonical via files_to_create",
        "description": "Read the current expedition report and verify it correctly lists all unmet PEV expectations before proceeding with any fixes.",
        "pev": {
            "perceive": "Examine spoke_expediter.py score_lug_quality to understand PEV key fallback logic.",
            "execute": "1. Read score_lug_quality. 2. Add fallbacks for description/issue/summary and nested pev fields. 3. Add fallbacks for files_to_create. 4. Run unit tests.",
            "verify": "Unit tests pass; non-canonical lug scores at least 8/10.",
        },
        "acceptance_criteria": ["files_to_create recognized as target_files fallback"],
        "files_to_create": ["WAI-Harness/spoke/managed/tests/test_spoke_expediter_noncanonical_pev.py"],
        "model_fit": "haiku",
    }


# ---------------------------------------------------------------------------
# Tests: score_lug_quality non-canonical key fallbacks
# ---------------------------------------------------------------------------

class TestNonCanonicalPEVKeys:

    def test_issue_key_satisfies_perceive(self):
        lug = _noncanonical_lug()
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert "perceive" not in missing, f"'issue' key should satisfy perceive; missing={missing}"

    def test_nested_pev_execute_satisfies_execute(self):
        lug = _noncanonical_lug()
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert "execute" not in missing, f"nested pev.execute should satisfy execute; missing={missing}"
        assert "execute_too_vague" not in missing, f"pev.execute content is long enough; missing={missing}"

    def test_nested_pev_verify_satisfies_verify(self):
        lug = _noncanonical_lug()
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert "verify" not in missing, f"nested pev.verify should satisfy verify; missing={missing}"

    def test_files_to_modify_satisfies_target_files(self):
        lug = _noncanonical_lug()
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert "target_files" not in missing, f"files_to_modify should satisfy target_files; missing={missing}"

    def test_noncanonical_lug_scores_full_pev_zero_core_missing(self):
        """The canonical AC: a lug with content only under non-canonical keys must
        have ZERO core PEV fields in missing_fields."""
        lug = _noncanonical_lug()
        score, missing = spoke_expediter.score_lug_quality(lug)
        core_missing = set(missing) & {"perceive", "execute", "verify"}
        assert core_missing == set(), (
            f"Full-scope lug should have no core PEV fields missing; missing={missing}"
        )

    def test_noncanonical_lug_scores_at_least_8(self):
        """A well-defined non-canonical lug with model_fit=haiku should score >=8."""
        lug = _noncanonical_lug()
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert score >= 8, f"Non-canonical lug should score >=8; got score={score}, missing={missing}"

    def test_summary_key_satisfies_perceive(self):
        lug = _noncanonical_lug_summary_description()
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert "perceive" not in missing, f"'summary' key should satisfy perceive; missing={missing}"

    def test_file_targets_satisfies_target_files(self):
        lug = _noncanonical_lug_summary_description()
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert "target_files" not in missing, f"'file_targets' should satisfy target_files; missing={missing}"

    def test_description_key_satisfies_perceive(self):
        lug = _noncanonical_lug_files_to_create()
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert "perceive" not in missing, f"'description' key should satisfy perceive; missing={missing}"

    def test_pev_perceive_satisfies_perceive(self):
        lug = _noncanonical_lug_files_to_create()
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert "perceive" not in missing, f"nested pev.perceive should satisfy perceive; missing={missing}"

    def test_files_to_create_satisfies_target_files(self):
        lug = _noncanonical_lug_files_to_create()
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert "target_files" not in missing, f"'files_to_create' should satisfy target_files; missing={missing}"

    def test_genuinely_empty_lug_still_flags(self):
        """Lugs with no scope content must still be flagged — fallbacks must not
        suppress legitimate missing-PEV signals."""
        lug = {
            "id": "empty-lug-001",
            "type": "implementation",
            "status": "open",
            "title": "Empty lug",
            "model_fit": "haiku",
        }
        score, missing = spoke_expediter.score_lug_quality(lug)
        core_missing = set(missing) & {"perceive", "execute", "verify"}
        assert core_missing == {"perceive", "execute", "verify"}, (
            f"Genuinely empty lug must flag all core PEV fields; missing={missing}"
        )

    def test_short_content_still_flags(self):
        """Content below the length threshold must still trigger missing-PEV."""
        lug = {
            "id": "short-content-001",
            "type": "implementation",
            "status": "open",
            "title": "Short content lug",
            "issue": "Too short",  # < 10 chars
            "execute": "Do it",    # < 100 chars — too vague
            "pev": {"verify": "ok"},  # < 10 chars
            "model_fit": "haiku",
        }
        score, missing = spoke_expediter.score_lug_quality(lug)
        assert "perceive" in missing, "Short issue (<10 chars) should still flag perceive"
        assert "verify" in missing, "Short pev.verify (<10 chars) should still flag verify"


# ---------------------------------------------------------------------------
# Tests: SKIP_TYPES excludes informational note types
# ---------------------------------------------------------------------------

class TestSkipTypes:

    def test_needs_you_note_in_skip_types(self):
        assert "needs_you_note" in spoke_expediter.SKIP_TYPES, (
            "needs_you_note must be in SKIP_TYPES so it never reaches the PEV gate"
        )

    def test_needs_you_in_skip_types(self):
        assert "needs_you" in spoke_expediter.SKIP_TYPES

    def test_note_in_skip_types(self):
        assert "note" in spoke_expediter.SKIP_TYPES

    def test_notice_in_skip_types(self):
        assert "notice" in spoke_expediter.SKIP_TYPES
