"""Acceptance proof: gap_exposure_validator.py — gap exposure + survey completeness (AC46)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import gap_exposure_validator as gev  # noqa: E402


def test_known_gap_types_have_surfaces():
    gaps = [{"gap_type": "test-null"}, {"gap_type": "capability-missing"},
            {"gap_type": "cruft/misplacement"}]
    res = gev.validate_gap_exposure(gaps)
    assert res["ok"] is True
    assert all(e.get("surface") for e in res["exposed"])


def test_unknown_gap_type_is_hidden():
    res = gev.validate_gap_exposure([{"gap_type": "mystery"}, {"gap_type": "test-null"}])
    assert res["ok"] is False
    assert len(res["hidden"]) == 1 and res["hidden"][0]["gap_type"] == "mystery"


def test_dropped_lug_without_reason_is_gap_hidden():
    lugs = [
        {"id": "l1", "closes_epic_acs": [{"ac": "AC1"}]},            # closes AC -> fine
        {"id": "l2", "closes_no_ac": "supporting context"},          # dropped w/ reason -> fine
        {"id": "l3", "decision_rationale": "scaffolding for l1"},     # dropped w/ rationale -> fine
        {"id": "l4"},                                                 # dropped, NO reason -> hidden
    ]
    res = gev.validate_dropped_lugs(lugs)
    assert res["ok"] is False and res["hidden"] == ["l4"]


def test_survey_completeness_typed_gaps_and_coverage():
    manifest = [
        {"path": "tools/a.py", "tested": True},      # mapped + tested
        {"path": "tools/b.py", "tested": False},     # mapped, untested -> path-untested
        {"path": "tools/orphan.py", "tested": True}, # not in CG -> cruft/misplacement
        {"path": "trash_bin/old.py", "tested": False},  # trash -> ignored
    ]
    cg = [
        {"id": "cap-a", "file_paths": ["tools/a.py"], "verification_ref": "tests/test_a.py"},
        {"id": "cap-b", "file_paths": ["tools/b.py"], "verification_ref": "tests/test_b.py"},
        {"id": "cap-c", "file_paths": ["tools/c.py"]},  # no verification_ref -> test-null
    ]
    res = gev.survey_completeness(manifest, cg)
    assert res["total"] == 3  # trash excluded
    assert res["coverage_pct"] == round(100.0 * 1 / 3, 1)  # only a.py is mapped+tested
    kinds = sorted(g["gap_type"] for g in res["gaps"])
    assert kinds == ["cruft/misplacement", "path-untested", "test-null"]
    assert res["orphans"] == ["tools/orphan.py"]
    assert res["exposure_ok"] is True  # all produced gaps are on a known surface


def test_full_coverage_no_gaps():
    manifest = [{"path": "tools/a.py", "tested": True}]
    cg = [{"id": "cap-a", "file_paths": ["tools/a.py"], "verification_ref": "tests/test_a.py"}]
    res = gev.survey_completeness(manifest, cg)
    assert res["coverage_pct"] == 100.0 and res["gaps"] == []
