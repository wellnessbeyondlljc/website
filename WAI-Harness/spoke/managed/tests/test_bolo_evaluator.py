"""
Tests for BOLO Evaluator and Registry
"""

import pytest
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.live.session_hook import SessionHook, SessionTurn
from src.bolo.registry import BOLORegistry, BOLOPattern, FRAMEWORK_BOLOS
from src.bolo.evaluator import BOLOEvaluator, BOLOAssessment, BOLOHit


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestBOLORegistry:

    def test_loads_framework_defaults(self):
        registry = BOLORegistry(load_framework_defaults=True)
        patterns = registry.all_patterns()
        assert len(patterns) >= len(FRAMEWORK_BOLOS)

    def test_empty_registry(self):
        registry = BOLORegistry(load_framework_defaults=False)
        assert registry.all_patterns() == []

    def test_add_and_get(self):
        registry = BOLORegistry(load_framework_defaults=False)
        pattern = BOLOPattern(
            pattern_id="test-pattern",
            name="Test Pattern",
            description="A test pattern.",
            keywords=["test", "example"],
            category="test",
            severity="low",
            action="note",
        )
        registry.add(pattern)
        retrieved = registry.get("test-pattern")
        assert retrieved is not None
        assert retrieved.name == "Test Pattern"

    def test_remove(self):
        registry = BOLORegistry(load_framework_defaults=False)
        pattern = BOLOPattern(
            pattern_id="to-remove",
            name="Remove Me",
            description="",
            keywords=["remove"],
            category="test",
            severity="low",
            action="note",
        )
        registry.add(pattern)
        assert registry.remove("to-remove") is True
        assert registry.get("to-remove") is None

    def test_remove_nonexistent(self):
        registry = BOLORegistry(load_framework_defaults=False)
        assert registry.remove("does-not-exist") is False

    def test_by_category(self):
        registry = BOLORegistry(load_framework_defaults=True)
        anti_patterns = registry.by_category("anti-pattern")
        assert len(anti_patterns) > 0
        for p in anti_patterns:
            assert p.category == "anti-pattern"

    def test_by_severity(self):
        registry = BOLORegistry(load_framework_defaults=True)
        high = registry.by_severity("high")
        for p in high:
            assert p.severity == "high"

    def test_load_from_taste(self):
        registry = BOLORegistry(load_framework_defaults=False)
        taste_bolos = [
            {
                "pattern_id": "taste-bolo-1",
                "name": "Taste BOLO 1",
                "keywords": ["taste", "specific"],
                "category": "taste",
                "severity": "medium",
                "action": "flag",
            }
        ]
        loaded = registry.load_from_taste(taste_bolos)
        assert loaded == 1
        p = registry.get("taste-bolo-1")
        assert p is not None
        assert p.source == "taste"

    def test_load_from_taste_skips_malformed(self):
        registry = BOLORegistry(load_framework_defaults=False)
        malformed = [{"no_pattern_id": "bad"}, {"pattern_id": "ok", "name": "OK", "keywords": []}]
        loaded = registry.load_from_taste(malformed)
        assert loaded == 1  # only the valid one

    def test_summary(self):
        registry = BOLORegistry(load_framework_defaults=True)
        summary = registry.summary()
        assert "total_patterns" in summary
        assert summary["total_patterns"] >= len(FRAMEWORK_BOLOS)


# ---------------------------------------------------------------------------
# Evaluator tests
# ---------------------------------------------------------------------------

class TestBOLOEvaluator:

    def _make_turn(self, user_input: str, response: str = "I'll help with that.") -> SessionTurn:
        hook = SessionHook("test_session")
        return hook.capture_turn(user_input=user_input, assistant_response=response)

    def test_clean_turn_no_hits(self):
        registry = BOLORegistry(load_framework_defaults=True)
        evaluator = BOLOEvaluator(registry)
        turn = self._make_turn("Please implement the feature.", "Done.")
        result = evaluator.assess(turn)
        assert result["risk_level"] == "none"
        assert result["hit_count"] == 0
        assert result["patterns_detected"] == []

    def test_scope_drift_detected(self):
        registry = BOLORegistry(load_framework_defaults=True)
        evaluator = BOLOEvaluator(registry)
        # "while I'm here" triggers scope drift
        turn = self._make_turn(
            "Can you fix the bug?",
            "Sure! Also, while I'm here I'll refactor the whole module.",
        )
        result = evaluator.assess(turn)
        assert result["risk_level"] in ("low", "medium", "high")
        assert any("scope" in pid.lower() for pid in result["patterns_detected"])

    def test_placeholder_lug_detected(self):
        registry = BOLORegistry(load_framework_defaults=True)
        evaluator = BOLOEvaluator(registry)
        turn = self._make_turn(
            "Create the lug.",
            "Created! TODO: fill in the PEV later.",
        )
        result = evaluator.assess(turn)
        assert result["risk_level"] == "high"
        assert "bolo-placeholder-lug" in result["patterns_detected"]

    def test_full_assessment(self):
        registry = BOLORegistry(load_framework_defaults=True)
        evaluator = BOLOEvaluator(registry)
        turn = self._make_turn("Stop and undo everything.", "Reverting now.")
        assessment = evaluator.assess_full(turn)
        assert isinstance(assessment, BOLOAssessment)
        assert assessment.turn_id == turn.turn_id

    def test_session_hits_accumulate(self):
        registry = BOLORegistry(load_framework_defaults=True)
        evaluator = BOLOEvaluator(registry)

        turn1 = self._make_turn("Fix the bug.", "Done.")
        turn2 = self._make_turn("Also TODO: add tests.", "Will do.")

        evaluator.assess(turn1)
        evaluator.assess(turn2)

        hits = evaluator.session_hits()
        # turn2 should have at least one hit (TODO)
        assert len(hits) >= 1

    def test_high_risk_turns(self):
        registry = BOLORegistry(load_framework_defaults=True)
        evaluator = BOLOEvaluator(registry)

        # Use a shared hook so turn IDs are distinct (turn_1, turn_2)
        hook = SessionHook("test_session")
        clean_turn = hook.capture_turn("Implement feature.", "Done.")
        risky_turn = hook.capture_turn(
            "Create a placeholder lug.", "Created a TODO placeholder."
        )

        evaluator.assess(clean_turn)
        evaluator.assess(risky_turn)

        high_risk = evaluator.high_risk_turns()
        assert risky_turn.turn_id in high_risk
        assert clean_turn.turn_id not in high_risk

    def test_summary(self):
        registry = BOLORegistry(load_framework_defaults=True)
        evaluator = BOLOEvaluator(registry)

        for text in ["Fix it.", "TODO: placeholder.", "Also while I'm here..."]:
            evaluator.assess(self._make_turn(text))

        summary = evaluator.summary()
        assert "total_turns_assessed" in summary
        assert summary["total_turns_assessed"] == 3
        assert "total_hits" in summary

    def test_custom_pattern(self):
        registry = BOLORegistry(load_framework_defaults=False)
        registry.add(BOLOPattern(
            pattern_id="custom-1",
            name="Custom Alert",
            description="Custom test alert.",
            keywords=["forbidden phrase"],
            category="custom",
            severity="high",
            action="escalate",
        ))
        evaluator = BOLOEvaluator(registry)
        turn = self._make_turn("Please use the forbidden phrase here.")
        result = evaluator.assess(turn)
        assert "custom-1" in result["patterns_detected"]
        assert result["risk_level"] == "high"

    def test_empty_registry_no_hits(self):
        registry = BOLORegistry(load_framework_defaults=False)
        evaluator = BOLOEvaluator(registry)
        turn = self._make_turn("Anything at all.", "Response.")
        result = evaluator.assess(turn)
        assert result["risk_level"] == "none"
        assert result["hit_count"] == 0
