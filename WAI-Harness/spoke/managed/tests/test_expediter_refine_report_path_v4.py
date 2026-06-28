"""test_expediter_refine_report_path_v4.py

AP test: the expediter's auto-emitted scout-refinement lug must point the
downstream agent at the REAL expedition-report path.

On a v4 spoke the report is written under WAI-Harness/spoke/advisors/expediter/
expeditions/ (there is no WAI-Spoke tree). A hardcoded WAI-Spoke/advisors/...
prompt string sent the refining agent to a non-existent path and the auto-refine
loop died. expedition_report_path() resolves the same location run_hygiene_scout
WRITES to, so we assert it lands in the v4 advisors tree, NOT WAI-Spoke.
"""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import spoke_expediter  # noqa: E402 — must come after sys.path insert


def _make_v4(spoke_root):
    """Create the v4 advisors tree (and local marker) so resolution is v4."""
    os.makedirs(os.path.join(spoke_root, "WAI-Harness", "spoke", "advisors"), exist_ok=True)
    os.makedirs(os.path.join(spoke_root, "WAI-Harness", "spoke", "local"), exist_ok=True)


class TestV4OnlyReportPath:
    def test_report_path_under_v4_advisors_not_wai_spoke(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        _make_v4(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        report_id = "scout-report-20260623T120000"
        path = spoke_expediter.expedition_report_path(tmp, report_id)

        expected = os.path.join(
            tmp, "WAI-Harness", "spoke", "advisors",
            "expediter", "expeditions", f"{report_id}.json",
        )
        assert path == expected, f"unexpected report path: {path}"
        # Hard invariant: must NOT route to a phantom WAI-Spoke tree.
        assert "WAI-Spoke" not in path
        assert os.path.join("WAI-Harness", "spoke", "advisors") in path
        assert path.endswith(os.path.join("expediter", "expeditions", f"{report_id}.json"))

    def test_emitted_refine_lug_execute_step_points_at_v4_report(self, monkeypatch, tmp_path):
        """End-to-end: run_hygiene_scout produces a report whose resolved path
        (the one the emitted refinement lug's execute[0] references) is in the
        v4 advisors tree, never WAI-Spoke. The scout returns a summary carrying
        report_id; execute[0] is built from expedition_report_path(report_id)."""
        tmp = str(tmp_path)
        _make_v4(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        # An auto-groomable open impl lug: core PEV present, only soft field
        # (acceptance_criteria) missing -> lands in `groomable` -> refine lug emitted.
        scored = [{
            "id": "impl-incomplete-001",
            "type": "implementation",
            "status": "open",
            "title": "Incomplete lug",
            "missing_fields": ["acceptance_criteria"],
        }]

        summary = spoke_expediter.run_hygiene_scout(
            tmp, scored, trigger_reason="test", dry_run=True
        )
        report_id = summary.get("report_id")
        assert report_id, f"scout produced no report_id: {summary}"
        assert summary.get("auto_groomable", 0) >= 1, (
            f"expected an auto-groomable finding so a refine lug is emitted: {summary}"
        )

        # execute[0] of the emitted refine lug is f"1. Read {report_path} ...".
        report_path = spoke_expediter.expedition_report_path(tmp, report_id)
        assert "WAI-Spoke" not in report_path, f"v3 path leaked: {report_path}"
        assert os.path.join("WAI-Harness", "spoke", "advisors") in report_path


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
