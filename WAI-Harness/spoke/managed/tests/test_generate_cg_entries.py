"""Acceptance proof: generate_cg_entries.py — auto-register commands into the CG (AC16 close)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import generate_cg_entries as gen  # noqa: E402
import audit_cg_registration as acr  # noqa: E402


def _mk(spoke, files):
    d = spoke / "templates" / "commands"; d.mkdir(parents=True)
    for name, body in files.items():
        (d / name).write_text(body)
    return spoke


def test_builds_entry_per_command_with_frontmatter(tmp_path):
    _mk(tmp_path, {
        "wai.md": "---\nname: wai\ndescription: Wakeup protocol briefing\n---\n# WAI\nbody",
        "wai-status.md": "# Quick health check\nbody",
    })
    entries = gen.build_entries(tmp_path)
    assert len(entries) == 2
    by_id = {e["id"]: e for e in entries}
    assert by_id["cap-wai"]["situation"] == "Wakeup protocol briefing"
    assert by_id["cap-wai"]["file_paths"] == ["templates/commands/wai.md"]
    assert by_id["cap-wai-status"]["situation"] == "Quick health check"  # heading fallback
    assert all(e["tier"] == "awareness" and e["kind"] == "command" for e in entries)


def test_merge_preserves_existing_curated_entries():
    existing = [{"id": "cap-wai", "name": "wai", "tier": "mandated", "file_paths": ["templates/commands/wai.md"]}]
    generated = [{"id": "cap-wai", "name": "wai", "tier": "awareness", "file_paths": ["templates/commands/wai.md"]},
                 {"id": "cap-new", "name": "new", "tier": "awareness", "file_paths": ["templates/commands/new.md"]}]
    merged = gen.merge_entries(existing, generated)
    by_id = {e["id"]: e for e in merged}
    assert by_id["cap-wai"]["tier"] == "mandated"  # existing curated tier wins
    assert "cap-new" in by_id and len(merged) == 2


def test_generated_entries_satisfy_registration_audit(tmp_path):
    _mk(tmp_path, {"a.md": "# A", "b.md": "# B", "c.md": "# C"})
    entries = gen.build_entries(tmp_path)
    discovered = acr.discover_commands(tmp_path)
    rep = acr.audit_registration(discovered, entries)
    assert rep["ok"] is True and rep["unregistered"] == []  # every command now registered
