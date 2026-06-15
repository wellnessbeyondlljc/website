"""Tests for tools/validate_teaching.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from validate_teaching import validate_teaching


def _valid():
    return {
        "id": "teaching-example-v1",
        "title": "Example teaching",
        "priority": "P2",
        "adopt_asap": False,
        "verification_steps": [
            {"id": "v1", "description": "Check file exists", "check": "test -f foo.txt", "pass_criteria": "exit 0"}
        ],
        "apply_steps": [
            {"id": "a1", "description": "Create file", "action": "touch foo.txt"}
        ],
    }


def test_valid_p2_teaching():
    assert validate_teaching(_valid()) == []


def test_valid_p0_teaching():
    d = _valid()
    d["priority"] = "P0"
    d["adopt_asap"] = True
    assert validate_teaching(d) == []


def test_valid_p1_teaching():
    d = _valid()
    d["priority"] = "P1"
    d["adopt_asap"] = True
    assert validate_teaching(d) == []


def test_valid_p3_teaching():
    d = _valid()
    d["priority"] = "P3"
    assert validate_teaching(d) == []


def test_missing_priority():
    d = _valid()
    del d["priority"]
    errors = validate_teaching(d)
    assert any("priority" in e for e in errors)


def test_invalid_priority():
    d = _valid()
    d["priority"] = "P5"
    errors = validate_teaching(d)
    assert any("priority" in e for e in errors)


def test_missing_adopt_asap():
    d = _valid()
    del d["adopt_asap"]
    errors = validate_teaching(d)
    assert any("adopt_asap" in e for e in errors)


def test_adopt_asap_wrong_for_p0():
    d = _valid()
    d["priority"] = "P0"
    d["adopt_asap"] = False  # should be True
    errors = validate_teaching(d)
    assert any("derivation mismatch" in e for e in errors)


def test_adopt_asap_wrong_for_p2():
    d = _valid()
    d["priority"] = "P2"
    d["adopt_asap"] = True  # should be False
    errors = validate_teaching(d)
    assert any("derivation mismatch" in e for e in errors)


def test_adopt_asap_non_bool():
    d = _valid()
    d["adopt_asap"] = "yes"
    errors = validate_teaching(d)
    assert any("adopt_asap" in e and "boolean" in e for e in errors)


def test_missing_verification_steps():
    d = _valid()
    del d["verification_steps"]
    errors = validate_teaching(d)
    assert any("verification_steps" in e for e in errors)


def test_empty_verification_steps():
    d = _valid()
    d["verification_steps"] = []
    errors = validate_teaching(d)
    assert any("verification_steps" in e and "at least one" in e for e in errors)


def test_verification_step_missing_field():
    d = _valid()
    d["verification_steps"] = [{"id": "v1", "description": "d"}]  # missing check + pass_criteria
    errors = validate_teaching(d)
    assert any("verification_steps[0]" in e and "check" in e for e in errors)
    assert any("verification_steps[0]" in e and "pass_criteria" in e for e in errors)


def test_missing_apply_steps():
    d = _valid()
    del d["apply_steps"]
    errors = validate_teaching(d)
    assert any("apply_steps" in e for e in errors)


def test_empty_apply_steps():
    d = _valid()
    d["apply_steps"] = []
    errors = validate_teaching(d)
    assert any("apply_steps" in e and "at least one" in e for e in errors)


def test_apply_step_missing_field():
    d = _valid()
    d["apply_steps"] = [{"id": "a1", "description": "d"}]  # missing action
    errors = validate_teaching(d)
    assert any("apply_steps[0]" in e and "action" in e for e in errors)


def test_multiple_errors_returned():
    d = {}
    errors = validate_teaching(d)
    assert len(errors) >= 4  # priority, adopt_asap, verification_steps, apply_steps all missing
