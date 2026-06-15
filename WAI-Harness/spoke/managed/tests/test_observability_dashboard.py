"""Acceptance proof: observability_dashboard.build_dashboard — oversight surfaces +
three-question confidence + freshness (AC37/AC38). Hermetic on a tmp spoke."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import observability_dashboard as od  # noqa: E402

NOW = "2026-06-10T07:30:00Z"


def test_dashboard_builds_with_surfaces_and_confidence(tmp_path):
    (tmp_path / "WAI-Spoke").mkdir()
    d = od.build_dashboard(str(tmp_path), now_ts=NOW)
    # AC37 oversight surfaces + AC38 three-question confidence model present
    assert "surfaces" in d and "confidence" in d
    assert d["generated_at"] and "2026-06-10T07:30:00" in d["generated_at"]  # echoes injected now_ts


def test_dashboard_carries_freshness_signal(tmp_path):
    (tmp_path / "WAI-Spoke").mkdir()
    d = od.build_dashboard(str(tmp_path), now_ts=NOW)
    # freshness/defect signal exists so a silently-stale surface can't read as current
    assert "observability_defects" in d
    assert isinstance(d["surfaces"], (dict, list))
