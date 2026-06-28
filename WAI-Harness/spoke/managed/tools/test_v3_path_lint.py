#!/usr/bin/env python3
"""Tests for the v3-path cut gate (impl-harness-parity-gate-at-cut-v1).

The gate is a RATCHET: a managed tool that references a v3 WAI-Spoke/ path with NO
v4-awareness is a soft-feature risk and must FAIL the cut unless allowlisted. A v4-aware
tool (WAI-Spoke/ only as a guarded fallback) passes. Proves: v3-only flagged, v4-aware
cleared, allowlist clears, exempt files skipped, and the manifest cut refuses + writes
nothing on a new violation.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v3_path_lint as L
import harness_upgrade as hu


def _managed(tmp_path, files):
    m = tmp_path / "managed"
    for rel, txt in files.items():
        p = m / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt)
    return m


def test_v3_only_tool_is_flagged(tmp_path):
    m = _managed(tmp_path, {"tools/bad.py": 'P = "WAI-Spoke/lugs/bytype"\nopen(P)\n'})
    rep = L.lint(m, allow_path=tmp_path / "none.json")
    assert rep["ok"] is False
    assert "tools/bad.py" in rep["violations"]


def test_v4_aware_tool_is_cleared(tmp_path):
    # references WAI-Spoke/ only as a guarded fallback beside a v4 resolution -> not flagged
    m = _managed(tmp_path, {"tools/ok.py":
        'import wai_paths\nbase = wai_paths.resolve_wai_root(".")\n'
        'V3 = "WAI-Spoke/lugs"  # fallback only\n'})
    rep = L.lint(m, allow_path=tmp_path / "none.json")
    assert rep["ok"] is True
    assert "tools/ok.py" not in rep["violations"]


def test_allowlist_clears_known_debt(tmp_path):
    m = _managed(tmp_path, {"tools/bad.py": 'P = "WAI-Spoke/lugs"\n'})
    (m / "tools" / "v3_path_lint_allow.json").write_text(
        json.dumps({"allow": {"tools/bad.py": "known debt"}}))
    rep = L.lint(m)  # default allowlist path under managed/tools/
    assert rep["ok"] is True
    assert "tools/bad.py" in rep["allowlisted_debt"]


def test_exempt_files_skipped(tmp_path):
    # the linter itself + test_* files name the pattern deliberately -> never flagged
    m = _managed(tmp_path, {
        "tools/test_something.py": 'P = "WAI-Spoke/lugs"\n',
        "tools/v3_path_lint.py": 'NEEDLE = "WAI-Spoke/"\n',
    })
    rep = L.lint(m, allow_path=tmp_path / "none.json")
    assert rep["ok"] is True


def test_comment_only_reference_ignored(tmp_path):
    m = _managed(tmp_path, {"tools/c.py": '# legacy lived at WAI-Spoke/lugs\nx = 1\n'})
    rep = L.lint(m, allow_path=tmp_path / "none.json")
    assert rep["ok"] is True


def test_manifest_cut_refuses_new_violation_and_writes_nothing(tmp_path):
    m = _managed(tmp_path, {"tools/bad.py": 'P = "WAI-Spoke/x"\nopen(P)\n'})
    assert not (m / hu.MANIFEST_NAME).exists()
    rc = hu.main(["manifest", "--managed", str(m), "--write"])
    assert rc == 1                              # cut refused
    assert not (m / hu.MANIFEST_NAME).exists()  # nothing written


def test_manifest_cut_proceeds_when_clean(tmp_path):
    m = _managed(tmp_path, {"tools/ok.py": 'import wai_paths\nx = 1\n'})
    rc = hu.main(["manifest", "--managed", str(m), "--write"])
    assert rc == 0
    assert (m / hu.MANIFEST_NAME).exists()


def test_manifest_cut_skip_lint_escape_hatch(tmp_path):
    m = _managed(tmp_path, {"tools/bad.py": 'P = "WAI-Spoke/x"\n'})
    rc = hu.main(["manifest", "--managed", str(m), "--write", "--skip-lint"])
    assert rc == 0
    assert (m / hu.MANIFEST_NAME).exists()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
