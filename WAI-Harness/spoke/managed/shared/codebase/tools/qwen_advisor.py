#!/usr/bin/env python3
"""qwen_advisor.py — Qwen Code configuration audit and safe remediation."""
from __future__ import annotations

import copy
import json
from pathlib import Path

SAFE_QWEN_SETTINGS = {
    "general": {"checkpointing": {"enabled": True}},
    "model": {
        "compressionThreshold": 0.4,
        "summarizeToolOutput": {
            "run_shell_command": {"tokenBudget": 1200},
        },
    },
    "context": {
        "fileName": ["QWEN.md", "AGENTS.md"],
        "includeDirectoryTree": False,
        "discoveryMaxDirs": 64,
        "fileFiltering": {
            "respectGitIgnore": True,
            "respectQwenIgnore": True,
            "enableRecursiveFileSearch": True,
        },
    },
}
SAFE_QWEN_IGNORE_PATTERNS = [
    "WAI-Spoke/sessions/",
    "WAI-Spoke/seed/",
    "WAI-Spoke/archive/",
    "WAI-Spoke/model-usage/",
    "WAI-Spoke/runtime/",
    "WAI-Spoke/WAI-LugIndex.jsonl",
    "WAI-Spoke/WAI-Lugs-archived.jsonl",
    "WAI-Spoke/WAI-State-extended.json",
    "docs/llm-full.txt",
]
QWEN_LOOP_GUARD_LINES = [
    "Treat this `QWEN.md` read as already satisfying the wakeup integration-file step.",
    "Do not re-read `QWEN.md` or rescan parent `QWEN.md` files during wakeup unless the user explicitly asks.",
]


# --- Utilities (duplicated to avoid circular imports with tool_advisor) ------

def read_text(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def load_json(path: Path, default=None):
    if not path.exists():
        return copy.deepcopy(default)
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return copy.deepcopy(default)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")


def normalize_with_trailing_newline(content: str) -> str:
    return content.rstrip() + "\n"


def deep_merge(base: dict, updates: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def ensure_brief_first_section(
    content: str, heading: str = "## Wakeup Convergence"
) -> tuple[str, bool]:
    lower = content.lower()
    if (
        "finish the wai point briefing before" in lower
        and "do not read full teaching bodies during wakeup" in lower
    ):
        return content, False

    block = (
        f"\n{heading}\n\n"
        "- Finish the WAI Point briefing before asking for approval on teachings or side actions.\n"
        "- During wakeup, summarize teachings from filenames/frontmatter only.\n"
        "- Do not read full teaching bodies during wakeup unless the user explicitly asks to review them now.\n"
    )
    return normalize_with_trailing_newline(content.rstrip() + block), True


# --- Qwen-specific functions -------------------------------------------------

def ensure_qwen_loop_guard(content: str) -> tuple[str, bool]:
    lower = content.lower()
    if (
        "do not re-read `qwen.md`" in lower
        and "already satisfying" in lower
        and "integration" in lower
    ):
        return content, False

    loop_block = (
        "\n## Loop Prevention\n\n"
        f"- {QWEN_LOOP_GUARD_LINES[0]}\n"
        f"- {QWEN_LOOP_GUARD_LINES[1]}\n"
    )
    return normalize_with_trailing_newline(content.rstrip() + loop_block), True


def ensure_qwen_md(
    project_root: Path, apply_changes: bool = True
) -> tuple[list[dict], list[dict], list[dict]]:
    qwen_path = project_root / "QWEN.md"
    findings: list[dict] = []
    fixes: list[dict] = []
    proposals: list[dict] = []
    if not qwen_path.exists():
        findings.append(
            {
                "area": "Qwen",
                "level": "warn",
                "code": "qwen-md-missing",
                "message": "QWEN.md missing",
            }
        )
        return findings, fixes, proposals

    content = read_text(qwen_path)
    new_content, changed = ensure_qwen_loop_guard(content)
    if changed:
        if apply_changes:
            write_text(qwen_path, new_content)
        fixes.append({"path": "QWEN.md", "action": "added Qwen loop-prevention guard"})

    lower = (new_content if changed else content).lower()
    if not changed and not (
        "do not re-read `qwen.md`" in lower
        and "already satisfying" in lower
        and "integration" in lower
    ):
        findings.append(
            {
                "area": "Qwen",
                "level": "fail",
                "code": "qwen-loop-guard-missing",
                "message": "QWEN.md lacks wakeup loop prevention",
            }
        )
    return findings, fixes, proposals


def ensure_qwen_convergence(
    project_root: Path, path: Path, apply_changes: bool = True
) -> tuple[list[dict], list[dict], list[dict]]:
    findings: list[dict] = []
    fixes: list[dict] = []
    proposals: list[dict] = []
    if not path.exists():
        return findings, fixes, proposals
    content = read_text(path)
    updated, changed = ensure_brief_first_section(content)
    if changed:
        if apply_changes:
            write_text(path, updated)
        fixes.append(
            {
                "path": str(path.relative_to(project_root)),
                "action": "normalized Qwen wakeup guidance",
            }
        )
    return findings, fixes, proposals


def ensure_qwen_settings(
    project_root: Path, apply_changes: bool = True
) -> tuple[list[dict], list[dict]]:
    settings_path = project_root / ".qwen" / "settings.json"
    before = load_json(settings_path, {})
    after = deep_merge(before, SAFE_QWEN_SETTINGS)
    if before != after:
        if apply_changes:
            write_json(settings_path, after)
        return [
            {
                "path": str(settings_path.relative_to(project_root)),
                "action": "updated Qwen settings",
            }
        ], []
    return [], []


def ensure_qwen_ignore(
    project_root: Path, apply_changes: bool = True
) -> tuple[list[dict], list[dict]]:
    ignore_path = project_root / ".qwenignore"
    lines = ignore_path.read_text().splitlines() if ignore_path.exists() else []
    existing = {line.strip() for line in lines if line.strip()}
    missing = [
        pattern for pattern in SAFE_QWEN_IGNORE_PATTERNS if pattern not in existing
    ]
    if not missing:
        return [], []
    updated = lines[:]
    if updated and updated[-1].strip():
        updated.append("")
    updated.extend(missing)
    if apply_changes:
        write_text(ignore_path, "\n".join(updated).rstrip() + "\n")
    return [
        {
            "path": str(ignore_path.relative_to(project_root)),
            "action": "extended .qwenignore",
        }
    ], []


def run_qwen_audit(
    project_root: Path, apply_changes: bool = True
) -> tuple[str, list[dict], list[dict], list[dict]]:
    findings: list[dict] = []
    fixes: list[dict] = []
    proposals: list[dict] = []
    active = (project_root / "QWEN.md").exists() or (project_root / ".qwen").exists()
    if not active:
        return "skip", findings, fixes, proposals

    md_findings, md_fixes, md_proposals = ensure_qwen_md(
        project_root, apply_changes=apply_changes
    )
    findings.extend(md_findings)
    fixes.extend(md_fixes)
    proposals.extend(md_proposals)

    settings_fixes, _ = ensure_qwen_settings(project_root, apply_changes=apply_changes)
    fixes.extend(settings_fixes)

    ignore_fixes, _ = ensure_qwen_ignore(project_root, apply_changes=apply_changes)
    fixes.extend(ignore_fixes)

    for path in [
        project_root / "QWEN.md",
        project_root / "templates" / "spoke" / "QWEN.md",
        project_root / "templates" / "qwen" / "QWEN.md",
    ]:
        path_findings, path_fixes, path_proposals = ensure_qwen_convergence(
            project_root, path, apply_changes=apply_changes
        )
        findings.extend(path_findings)
        fixes.extend(path_fixes)
        proposals.extend(path_proposals)

    status = "pass" if not any(f["level"] == "fail" for f in findings) else "fail"
    return status, findings, fixes, proposals
