"""test_archie_advisor_v4_paths.py

AP test: archie_advisor resolves its advisors-registry / schedule / state / runs
paths against WAI_HARNESS_MODE — and on a v4-only spoke targets the
WAI-Harness/spoke/advisors tree, NOT a phantom WAI-Spoke/advisors.

Invariants:
  1. WAI_HARNESS_MODE=v4-only on a v4 fixture -> _advisors_dir + the registry /
     schedule / state / runs paths all live under WAI-Harness/spoke/advisors and
     contain NO "WAI-Spoke" segment.
  2. completeness_scan actually reads the v4 registry (a stub advisor placed only
     in the v4 tree is found) — proving it did not no-op on a phantom v3 path.
  3. v3 fixture (explicit v3-only) -> paths resolve under WAI-Spoke/advisors
     (semantics preserved).
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import archie_advisor  # noqa: E402 — must come after sys.path insert


def _make_v4_tree(spoke_root):
    adv = os.path.join(spoke_root, "WAI-Harness", "spoke", "advisors")
    os.makedirs(adv, exist_ok=True)
    # local/ marker => v4-activated
    os.makedirs(os.path.join(spoke_root, "WAI-Harness", "spoke", "local"), exist_ok=True)
    return adv


def _make_v3_tree(spoke_root):
    adv = os.path.join(spoke_root, "WAI-Spoke", "advisors")
    os.makedirs(adv, exist_ok=True)
    return adv


class TestV4OnlyMode:
    def test_advisors_dir_targets_v4(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        adv = _make_v4_tree(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        resolved = archie_advisor._advisors_dir(tmp)
        assert os.path.abspath(resolved) == os.path.abspath(adv)
        assert "WAI-Spoke" not in resolved

    def test_path_helpers_target_v4(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        adv = _make_v4_tree(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        for fn in (
            archie_advisor._registry_path,
            archie_advisor._schedule_index_path,
            archie_advisor._archie_state_path,
            archie_advisor._archie_runs_path,
        ):
            p = fn(tmp)
            assert os.path.abspath(p).startswith(os.path.abspath(adv)), p
            assert "WAI-Spoke" not in p, p

    def test_completeness_scan_reads_v4_registry(self, monkeypatch, tmp_path):
        """A stub advisor placed only in the v4 advisors tree is detected — proves
        the scan resolved the v4 registry rather than no-op'ing on a phantom path."""
        tmp = str(tmp_path)
        adv = _make_v4_tree(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")

        # 30-day-old stub advisor -> completeness_scan must emit a "stub" finding
        registry = [{
            "advisor_id": "ghost",
            "status": "stub",
            "created_at": "2020-01-01T00:00:00+00:00",
        }]
        with open(os.path.join(adv, "registry.json"), "w") as fh:
            json.dump(registry, fh)

        findings = archie_advisor.completeness_scan(tmp)
        assert any("ghost" in f.title and "stub" in f.title for f in findings), \
            [f.title for f in findings]

    def test_wai_state_path_targets_v4(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        _make_v4_tree(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v4-only")
        p = archie_advisor._wai_state_path(tmp)
        assert "WAI-Spoke" not in p
        assert os.path.join("WAI-Harness", "spoke", "local") in p


class TestV3OnlyMode:
    def test_advisors_dir_targets_v3(self, monkeypatch, tmp_path):
        tmp = str(tmp_path)
        adv = _make_v3_tree(tmp)
        monkeypatch.setenv("WAI_HARNESS_MODE", "v3-only")

        resolved = archie_advisor._advisors_dir(tmp)
        assert os.path.abspath(resolved) == os.path.abspath(adv)
        assert resolved.endswith(os.path.join("WAI-Spoke", "advisors"))
