#!/usr/bin/env python3
"""
WAI Spoke Health Check

Validates a spoke against all framework expectations.
Run against any spoke directory to find drift, stale files, schema violations.

Usage:
  python3 tools/spoke_health_check.py /path/to/spoke          # full check
  python3 tools/spoke_health_check.py /path/to/spoke --quick   # wakeup-weight (<2s)
  python3 tools/spoke_health_check.py .                        # check current dir
  python3 tools/spoke_health_check.py . --json                 # machine output
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

# Add tools dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.wai_validate import (
    RETIRED_FILES,
    RETIRED_OBJECT_REFS,
    validate_bytype_structure,
    validate_lug,
    validate_lug_file_location,
    validate_skill_entry,
    validate_wai_state,
)


class Check:
    """Single health check result."""

    def __init__(self, check_id: str, category: str, status: str, detail: str):
        self.id = check_id
        self.category = category
        self.status = status  # PASS, FAIL, WARN, SKIP
        self.detail = detail

    def to_dict(self):
        return {
            "id": self.id,
            "category": self.category,
            "status": self.status,
            "detail": self.detail,
        }


class HealthReport:
    """Collection of health check results."""

    def __init__(self, spoke_path: str, mode: str):
        self.spoke_path = spoke_path
        self.mode = mode
        self.checks: list[Check] = []
        self.start_time = time.time()

    def add(self, check_id: str, category: str, status: str, detail: str):
        self.checks.append(Check(check_id, category, status, detail))

    @property
    def passed(self):
        return sum(1 for c in self.checks if c.status == "PASS")

    @property
    def failed(self):
        return sum(1 for c in self.checks if c.status == "FAIL")

    @property
    def warnings(self):
        return sum(1 for c in self.checks if c.status == "WARN")

    @property
    def elapsed_ms(self):
        return (time.time() - self.start_time) * 1000

    @property
    def health(self):
        """Overall health: GREEN (0 fails), YELLOW (1-3 fails), RED (4+ fails).
        WARNs are informational and do not affect health status."""
        if self.failed == 0:
            return "GREEN"
        elif self.failed <= 3:
            return "YELLOW"
        else:
            return "RED"

    def to_dict(self):
        return {
            "spoke_path": self.spoke_path,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "mode": self.mode,
            "health": self.health,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "checks": [c.to_dict() for c in self.checks],
        }

    def print_text(self):
        print(f"\n{'=' * 65}")
        print(f"  WAI Spoke Health Check — {self.mode} mode")
        print(f"  Spoke: {self.spoke_path}")
        print(f"{'=' * 65}")

        current_cat = None
        for c in self.checks:
            if c.category != current_cat:
                current_cat = c.category
                print(f"\n  [{current_cat}]")
            icon = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "SKIP": "—"}[c.status]
            print(f"    {icon} {c.id}: {c.detail}")

        print(f"\n{'─' * 65}")
        print(
            f"  Passed: {self.passed} | Failed: {self.failed} | "
            f"Warnings: {self.warnings} | {self.elapsed_ms:.0f}ms"
        )
        print(f"  Health: {self.health}")
        print()


# ─── Check Categories ────────────────────────────────────────────────────────


def check_structure(report: HealthReport, wai_spoke: Path):
    """Category 1: Core structure validation."""
    cat = "structure"

    # WAI-State.json
    state_file = wai_spoke / "WAI-State.json"
    if not state_file.exists():
        report.add("structure-wai-state", cat, "FAIL", "WAI-State.json not found")
        return  # Can't continue without state

    try:
        state = json.loads(state_file.read_text())
        violations = validate_wai_state(state)
        warnings = [v for v in violations if v.startswith("WARNING")]
        errors = [v for v in violations if not v.startswith("WARNING")]
        if errors:
            report.add("structure-wai-state", cat, "FAIL", f"{len(errors)} violations: {errors[0]}")
        elif warnings:
            report.add("structure-wai-state", cat, "WARN", warnings[0])
        else:
            report.add("structure-wai-state", cat, "PASS", "WAI-State.json valid")
    except json.JSONDecodeError as e:
        report.add("structure-wai-state", cat, "FAIL", f"WAI-State.json invalid JSON: {e}")

    # WAI-Skills.jsonl
    skills_file = wai_spoke / "skills" / "WAI-Skills.jsonl"
    if not skills_file.exists():
        report.add("structure-skills-jsonl", cat, "FAIL", "WAI-Skills.jsonl not found")
    else:
        try:
            count = 0
            for line in skills_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                json.loads(line)
                count += 1
            report.add("structure-skills-jsonl", cat, "PASS", f"WAI-Skills.jsonl valid ({count} entries)")
        except json.JSONDecodeError as e:
            report.add("structure-skills-jsonl", cat, "FAIL", f"WAI-Skills.jsonl parse error: {e}")

    # bytype structure
    violations = validate_bytype_structure(wai_spoke)
    if violations:
        report.add("structure-bytype", cat, "FAIL", f"{len(violations)} issues: {violations[0]}")
    else:
        report.add("structure-bytype", cat, "PASS", "bytype/ hierarchy complete")

    # sessions directory
    sessions = wai_spoke / "sessions"
    if sessions.exists():
        report.add("structure-sessions", cat, "PASS", "sessions/ exists")
    else:
        report.add("structure-sessions", cat, "FAIL", "sessions/ missing")

    # seed/ingest
    ingest = wai_spoke / "seed" / "ingest"
    processed = wai_spoke / "seed" / "ingest" / "processed"
    if ingest.exists() and processed.exists():
        report.add("structure-seed", cat, "PASS", "seed/ingest/ + processed/ exist")
    else:
        report.add("structure-seed", cat, "FAIL", "seed/ingest/ or processed/ missing")


def check_stale_files(report: HealthReport, wai_spoke: Path):
    """Category 2: Detect retired/stale files that should not exist."""
    cat = "stale-files"

    for retired in RETIRED_FILES:
        path = wai_spoke / retired
        if path.exists():
            # Check if it's truly stale (has content beyond a retirement header)
            content = path.read_text().strip()
            lines = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]
            if lines:
                report.add(f"stale-{retired}", cat, "FAIL", f"{retired} exists with {len(lines)} data lines (should be retired)")
            else:
                report.add(f"stale-{retired}", cat, "WARN", f"{retired} exists but empty/header-only — safe to delete")
        else:
            report.add(f"stale-{retired}", cat, "PASS", f"{retired} correctly absent")

    # Check for retired lugs/active/ directory
    active_dir = wai_spoke / "lugs" / "active"
    if active_dir.exists():
        report.add("stale-lugs-active", cat, "FAIL", "lugs/active/ exists (retired — use bytype/)")
    else:
        report.add("stale-lugs-active", cat, "PASS", "lugs/active/ correctly absent")


def check_skill_registry(report: HealthReport, wai_spoke: Path):
    """Category 3: Skill registry consistency."""
    cat = "skill-registry"

    skills_file = wai_spoke / "skills" / "WAI-Skills.jsonl"
    if not skills_file.exists():
        report.add("registry-file", cat, "SKIP", "WAI-Skills.jsonl not found — skipping")
        return

    skills_dir = wai_spoke / "skills"
    entries = []
    for line in skills_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    # Check for retired object references
    retired_refs = []
    for entry in entries:
        for obj in entry.get("objects", []):
            if obj in RETIRED_OBJECT_REFS:
                retired_refs.append(f"{entry.get('id', '?')}: references '{obj}'")

    if retired_refs:
        report.add("registry-retired-refs", cat, "FAIL",
                    f"{len(retired_refs)} retired object refs: {retired_refs[0]}")
    else:
        report.add("registry-retired-refs", cat, "PASS", "No retired object references")

    # Check each entry has matching skills/{id}/ dir
    missing_dirs = []
    for entry in entries:
        skill_id = entry.get("id", "")
        skill_dir = skills_dir / skill_id
        if not skill_dir.exists():
            missing_dirs.append(skill_id)

    if missing_dirs:
        report.add("registry-dirs", cat, "WARN",
                    f"{len(missing_dirs)} skills without local dirs: {', '.join(missing_dirs[:5])}")
    else:
        report.add("registry-dirs", cat, "PASS", "All registered skills have local dirs")

    # Check for orphan skill dirs (dirs not in registry)
    registered_ids = {e.get("id", "") for e in entries}
    orphan_dirs = []
    for d in skills_dir.iterdir():
        if d.is_dir() and d.name not in registered_ids and d.name != "__pycache__":
            orphan_dirs.append(d.name)

    if orphan_dirs:
        report.add("registry-orphans", cat, "WARN",
                    f"{len(orphan_dirs)} skill dirs not in registry: {', '.join(orphan_dirs[:5])}")
    else:
        report.add("registry-orphans", cat, "PASS", "No orphan skill directories")


def check_lug_integrity(report: HealthReport, wai_spoke: Path):
    """Category 4: Validate active lugs (full mode only)."""
    cat = "lug-integrity"

    bytype = wai_spoke / "lugs" / "bytype"
    if not bytype.exists():
        report.add("lug-bytype", cat, "SKIP", "bytype/ not found — skipping")
        return

    total = 0
    violations_count = 0
    missing_pev = 0
    misplaced = 0
    seen_ids = set()
    duplicate_ids = []

    for json_file in bytype.rglob("*.json"):
        parent = json_file.parent.name
        if parent not in ("open", "in_progress", "undelivered"):
            continue

        total += 1
        try:
            lug = json.loads(json_file.read_text())
        except json.JSONDecodeError:
            violations_count += 1
            continue

        lug_id = lug.get("i", lug.get("id", ""))
        if lug_id in seen_ids:
            duplicate_ids.append(lug_id)
        seen_ids.add(lug_id)

        violations = validate_lug(lug)
        location_violations = validate_lug_file_location(lug, json_file)

        if any("PEV" in v for v in violations):
            missing_pev += 1
        if location_violations:
            misplaced += 1
        if violations or location_violations:
            violations_count += 1

    # Report
    if violations_count == 0:
        report.add("lug-schema", cat, "PASS", f"All {total} active lugs valid")
    else:
        report.add("lug-schema", cat, "FAIL",
                    f"{violations_count}/{total} active lugs have violations")

    if missing_pev:
        report.add("lug-pev", cat, "FAIL", f"{missing_pev} actionable lugs missing PEV fields")
    else:
        report.add("lug-pev", cat, "PASS", "All actionable lugs have PEV fields")

    if misplaced:
        report.add("lug-location", cat, "FAIL", f"{misplaced} lugs in wrong bytype/ location")
    else:
        report.add("lug-location", cat, "PASS", "All lugs in correct bytype/ location")

    if duplicate_ids:
        report.add("lug-duplicates", cat, "FAIL",
                    f"{len(duplicate_ids)} duplicate IDs: {duplicate_ids[0]}")
    else:
        report.add("lug-duplicates", cat, "PASS", "No duplicate lug IDs")


def check_hub_connectivity(report: HealthReport, wai_spoke: Path):
    """Category 5: Hub path and connectivity (full mode only)."""
    cat = "hub"

    state_file = wai_spoke / "WAI-State.json"
    if not state_file.exists():
        report.add("hub-state", cat, "SKIP", "WAI-State.json not found")
        return

    state = json.loads(state_file.read_text())
    hub_path = state.get("wheel", {}).get("hub_path")

    if not hub_path:
        report.add("hub-path", cat, "WARN", "wheel.hub_path is null — hub not connected")
        return

    hub = Path(hub_path)
    if not hub.exists():
        report.add("hub-path", cat, "FAIL", f"hub_path '{hub_path}' does not exist")
        return

    report.add("hub-path", cat, "PASS", f"Hub reachable at {hub_path}")

    # teachings_repo
    teachings = hub / "teachings_repo" / "framework" / "current"
    if teachings.exists():
        count = len(list(teachings.glob("*.teaching")))
        report.add("hub-teachings", cat, "PASS", f"teachings_repo has {count} teachings")
    else:
        report.add("hub-teachings", cat, "FAIL", "teachings_repo/framework/current/ not found")

    # Signals inbox
    signals = hub / "WAI-Hub" / "signals" / "incoming"
    if signals.exists():
        report.add("hub-signals", cat, "PASS", "WAI-Hub/signals/incoming/ exists")
    else:
        report.add("hub-signals", cat, "FAIL", "WAI-Hub/signals/incoming/ not found")


def check_cc_hooks(report: HealthReport, wai_spoke: Path):
    """Category 6: Claude Code hook configuration — catches silent protocol failures."""
    cat = "cc-hooks"

    project_root = wai_spoke.parent
    settings_file = project_root / ".claude" / "settings.json"

    if not settings_file.exists():
        report.add("hooks-settings", cat, "FAIL", ".claude/settings.json not found")
        return

    try:
        settings = json.loads(settings_file.read_text())
    except json.JSONDecodeError as e:
        report.add("hooks-settings", cat, "FAIL", f".claude/settings.json invalid JSON: {e}")
        return

    hooks = settings.get("hooks", {})

    # Required hooks
    required_hooks = {
        "SessionStart": "Wakeup protocol trigger",
        "UserPromptSubmit": "Session guard + context injection",
        "PreToolUse": "Destructive command guard",
    }
    for hook_name, purpose in required_hooks.items():
        if hook_name in hooks and hooks[hook_name]:
            # Verify the script file exists
            entries = hooks[hook_name]
            script_ok = True
            for entry in entries:
                for h in entry.get("hooks", []):
                    cmd = h.get("command", "")
                    # Fail immediately if hook uses $CLAUDE_PROJECT_DIR — CC never sets this var
                    if "$CLAUDE_PROJECT_DIR" in cmd:
                        report.add(f"hooks-{hook_name.lower()}-env-var", cat, "FAIL",
                                   f"{hook_name} uses $CLAUDE_PROJECT_DIR — CC never sets this, hook silently fails")
                        script_ok = False
                        continue
                    # Verify the script file exists (absolute path)
                    if not Path(cmd).exists():
                        report.add(f"hooks-{hook_name.lower()}-script", cat, "FAIL",
                                   f"{hook_name} script missing: {cmd}")
                        script_ok = False
            if script_ok:
                report.add(f"hooks-{hook_name.lower()}", cat, "PASS",
                           f"{hook_name} configured — {purpose}")
        else:
            report.add(f"hooks-{hook_name.lower()}", cat, "FAIL",
                       f"{hook_name} NOT configured — {purpose}")

    # Recommended hooks
    recommended_hooks = {
        "Stop": "Test runner after responses",
        "PreCompact": "State preservation before compaction",
    }
    for hook_name, purpose in recommended_hooks.items():
        if hook_name in hooks and hooks[hook_name]:
            report.add(f"hooks-{hook_name.lower()}", cat, "PASS",
                       f"{hook_name} configured — {purpose}")
        else:
            report.add(f"hooks-{hook_name.lower()}", cat, "WARN",
                       f"{hook_name} not configured (recommended) — {purpose}")

    # Deny rules
    permissions = settings.get("permissions", {})
    deny = permissions.get("deny", [])
    if deny:
        report.add("hooks-deny-rules", cat, "PASS", f"{len(deny)} deny rules configured")
    else:
        report.add("hooks-deny-rules", cat, "FAIL", "No deny rules — destructive commands unguarded")

    # CLAUDE.md check
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        lines = len(claude_md.read_text().splitlines())
        if lines >= 50:
            report.add("hooks-claude-md", cat, "PASS", f"CLAUDE.md present ({lines} lines)")
        else:
            report.add("hooks-claude-md", cat, "WARN", f"CLAUDE.md underweight ({lines} lines, ideal 50+)")
    else:
        report.add("hooks-claude-md", cat, "FAIL", "CLAUDE.md not found")


def check_tool_config(report: HealthReport, wai_spoke: Path):
    """Category 7: Cross-tool config hygiene."""
    cat = "tool-config"

    project_root = wai_spoke.parent
    advisor_state = wai_spoke / "advisors" / "tool-advisor" / "scan_state.json"
    if advisor_state.exists():
        try:
            state = json.loads(advisor_state.read_text())
            if state.get("audit_pending"):
                detail = state.get("audit_reason") or "tool-advisor audit pending"
                report.add("tool-advisor-state", cat, "WARN", detail)
            else:
                report.add("tool-advisor-state", cat, "PASS", "tool-advisor state present and current")
        except json.JSONDecodeError as e:
            report.add("tool-advisor-state", cat, "FAIL", f"tool-advisor scan_state invalid JSON: {e}")
    else:
        report.add("tool-advisor-state", cat, "WARN", "tool-advisor scan_state missing")

    gemini_md = project_root / "GEMINI.md"
    if gemini_md.exists():
        content = gemini_md.read_text()
        lower = content.lower()
        if (
            "do not re-read `gemini.md`" in lower
            and "already satisfying" in lower
            and "integration" in lower
        ):
            report.add("tool-gemini-guard", cat, "PASS", "GEMINI.md has explicit loop-prevention guard")
        else:
            report.add("tool-gemini-guard", cat, "FAIL", "GEMINI.md lacks loop-prevention guard")

        gemini_settings = project_root / ".gemini" / "settings.json"
        if gemini_settings.exists():
            report.add("tool-gemini-settings", cat, "PASS", ".gemini/settings.json present")
        else:
            report.add("tool-gemini-settings", cat, "WARN", ".gemini/settings.json missing")

        gemini_ignore = project_root / ".geminiignore"
        if gemini_ignore.exists():
            report.add("tool-gemini-ignore", cat, "PASS", ".geminiignore present")
        else:
            report.add("tool-gemini-ignore", cat, "WARN", ".geminiignore missing")
    else:
        report.add("tool-gemini-guard", cat, "SKIP", "GEMINI.md not present")

    wakeup_candidates = [
        project_root / "WAI-Spoke" / "commands" / "wai.md",
        project_root / "WAI-Spoke" / "skills" / "wai" / "wai.md",
        project_root / "templates" / "commands" / "wai.md",
        project_root / "templates" / "spoke" / "skills" / "wai" / "wai.md",
    ]
    existing = [path for path in wakeup_candidates if path.exists()]
    if existing:
        missing = []
        for path in existing:
            lower = path.read_text().lower()
            if (
                "integration file" in lower
                and "do not reopen the same integration file during wakeup" not in lower
                and "do not reopen the same file again during wakeup" not in lower
            ):
                missing.append(path.relative_to(project_root).as_posix())
        if missing:
            report.add("tool-wakeup-guard", cat, "FAIL", f"Wakeup guard missing in: {', '.join(missing[:3])}")
        else:
            report.add("tool-wakeup-guard", cat, "PASS", "Wakeup files include integration-file reentry guard")
    else:
        report.add("tool-wakeup-guard", cat, "SKIP", "No wakeup file found")

    agents_md = project_root / "AGENTS.md"
    if agents_md.exists():
        content = agents_md.read_text()
        if "WAI-Guide.md" in content:
            report.add("tool-codex-agents", cat, "FAIL", "AGENTS.md still references WAI-Guide.md")
        else:
            report.add("tool-codex-agents", cat, "PASS", "AGENTS.md avoids dead WAI-Guide reference")
    else:
        report.add("tool-codex-agents", cat, "SKIP", "AGENTS.md not present")


def check_platform(report: HealthReport, wai_spoke: Path):
    """Category 8: Platform compatibility (full mode only)."""
    cat = "platform"

    os_name = platform.system()
    report.add("platform-os", cat, "PASS", f"OS: {os_name} ({platform.release()})")

    # GNU date check (wai.md stale lug detection uses `date -d`)
    import subprocess
    try:
        result = subprocess.run(
            ["date", "-d", "4 hours ago", "+%s"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            report.add("platform-date", cat, "PASS", "GNU date -d supported")
        else:
            report.add("platform-date", cat, "WARN",
                        "GNU date -d not supported — stale lug detection in wai.md may fail")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        report.add("platform-date", cat, "WARN", "date command not available")


# ─── Main ────────────────────────────────────────────────────────────────────


def run_health_check(spoke_path: str, mode: str = "full") -> HealthReport:
    """Run health check and return report."""
    report = HealthReport(spoke_path, mode)
    path = Path(spoke_path).resolve()

    # Find WAI-Spoke
    if (path / "WAI-Spoke").exists():
        wai_spoke = path / "WAI-Spoke"
    elif path.name == "WAI-Spoke":
        wai_spoke = path
    else:
        report.add("init", "structure", "FAIL", f"No WAI-Spoke/ found at {path}")
        return report

    # Always run: structure, stale files, skill registry
    check_structure(report, wai_spoke)
    check_stale_files(report, wai_spoke)
    check_skill_registry(report, wai_spoke)

    # Always run: CC hook configuration
    check_cc_hooks(report, wai_spoke)
    check_tool_config(report, wai_spoke)

    # Full mode: also run lug integrity, hub, platform
    if mode == "full":
        check_lug_integrity(report, wai_spoke)
        check_hub_connectivity(report, wai_spoke)
        check_platform(report, wai_spoke)

    return report


def main():
    parser = argparse.ArgumentParser(description="WAI Spoke Health Check")
    parser.add_argument("spoke_path", nargs="?", default=".",
                        help="Path to spoke directory (default: .)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode — structure, stale files, registry only")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON report")

    args = parser.parse_args()
    mode = "quick" if args.quick else "full"

    report = run_health_check(args.spoke_path, mode)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        report.print_text()

    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
