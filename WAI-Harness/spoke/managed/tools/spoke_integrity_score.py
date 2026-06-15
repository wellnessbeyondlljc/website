#!/usr/bin/env python3
"""
spoke_integrity_score.py — Composite spoke integrity score (0-100)

Five dimensions (20pts each):
  1. structure  — WAI-State.json, Skills, bytype/, sessions/, seed/
  2. hooks      — all 5 hooks configured, no env vars in commands
  3. lugs       — PEV present on actionable lugs, no location violations
  4. parity     — matches hub parity head (uses spoke_parity_check)
  5. hub        — hub reachable, teachings current (0 unprocessed)

Designed for Tender, session-start.sh, and human review.
Exit codes: 0 = healthy (>=80), 1 = degraded (50-79), 2 = critical (<50)
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wai_paths  # noqa: E402  harness-mode root resolver (single source of truth)


def _wai_base(spoke: Path) -> Path:
    """Resolve the active WAI working-base for this spoke (harness-mode-aware).
    Returns WAI-Harness/spoke/local in v4-only, WAI-Spoke in v3/coexist/auto.
    Falls back to WAI-Spoke if the resolver returns None (no tree present)."""
    base, _mode = wai_paths.resolve_wai_root(str(spoke))
    if base is not None:
        return Path(base)
    return spoke / "WAI-Spoke"


def score_structure(spoke: Path) -> tuple[int, list[str]]:
    """Max 20 pts. Each required file/dir = 4pts."""
    score = 0
    notes = []
    base = _wai_base(spoke)
    checks = [
        (base / "WAI-State.json", "WAI-State.json"),
        (base / "skills" / "WAI-Skills.jsonl", "WAI-Skills.jsonl"),
        (base / "lugs" / "bytype", "lugs/bytype/"),
        (base / "sessions", "sessions/"),
        (base / "seed" / "ingest", "seed/ingest/"),
    ]
    for path, label in checks:
        if path.exists():
            score += 4
        else:
            notes.append(f"missing: {label}")
    return score, notes


def score_hooks(spoke: Path) -> tuple[int, list[str]]:
    """Max 20 pts. 5 required hooks @ 4pts each, env-var penalty (-5)."""
    score = 0
    notes = []
    settings = spoke / ".claude" / "settings.json"
    if not settings.exists():
        return 0, ["settings.json missing"]

    with open(settings) as f:
        try:
            cfg = json.load(f)
        except json.JSONDecodeError:
            return 0, ["settings.json invalid JSON"]

    hooks = cfg.get("hooks", {})
    required = ["SessionStart", "UserPromptSubmit", "PreToolUse", "Stop", "PreCompact"]
    for h in required:
        if h in hooks:
            score += 4
        else:
            notes.append(f"missing hook: {h}")

    # Env var penalty
    raw = json.dumps(cfg)
    if "$CLAUDE_PROJECT_DIR" in raw:
        score = max(0, score - 5)
        notes.append("$CLAUDE_PROJECT_DIR in hook commands (use absolute paths)")

    # Skill sync gap penalty: templates/commands/wai-*.md newer than .claude/commands/
    templates_cmds = spoke / "templates" / "commands"
    claude_cmds = spoke / ".claude" / "commands"
    if templates_cmds.exists() and claude_cmds.exists():
        sync_gaps = []
        for src in templates_cmds.glob("wai*.md"):
            dst = claude_cmds / src.name
            if not dst.exists() or src.stat().st_mtime > dst.stat().st_mtime:
                sync_gaps.append(src.name)
        if sync_gaps:
            score = max(0, score - 2)
            notes.append(f"skill sync gap: {', '.join(sync_gaps[:3])}{'…' if len(sync_gaps) > 3 else ''} — run /shipit")

    return min(score, 20), notes


def score_lugs(spoke: Path) -> tuple[int, list[str]]:
    """Max 20 pts. Deductions for PEV violations and schema issues."""
    score = 20
    notes = []
    bytype = _wai_base(spoke) / "lugs" / "bytype"
    if not bytype.exists():
        return 0, ["lugs/bytype/ missing"]

    pev_violations = 0
    schema_violations = 0
    total_actionable = 0

    actionable_types = {"task", "bug", "feature", "implementation"}

    for ltype_dir in bytype.iterdir():
        if not ltype_dir.is_dir():
            continue
        ltype = ltype_dir.name
        for status_dir in ltype_dir.iterdir():
            if not status_dir.is_dir():
                continue
            for lug_file in status_dir.glob("*.json"):
                try:
                    with open(lug_file) as f:
                        lug = json.load(f)
                except (json.JSONDecodeError, OSError):
                    schema_violations += 1
                    continue

                # PEV check for actionable lugs
                if ltype in actionable_types and status_dir.name in ("open", "in_progress"):
                    total_actionable += 1
                    has_perceive = bool(lug.get("perceive"))
                    has_execute = bool(lug.get("execute"))
                    has_verify = bool(lug.get("verify"))
                    if not (has_perceive and has_execute and has_verify):
                        pev_violations += 1

    # Deductions: each PEV violation = -1pt (cap at -10)
    pev_deduct = min(pev_violations, 10)
    score -= pev_deduct
    if pev_violations:
        notes.append(f"{pev_violations}/{total_actionable} actionable lugs missing PEV")

    # Schema violations
    if schema_violations:
        score -= min(schema_violations * 2, 5)
        notes.append(f"{schema_violations} lug files with JSON errors")

    return max(0, score), notes


def score_parity(spoke: Path, hub_path: str) -> tuple[int, list[str]]:
    """Max 20 pts. At parity = 20, each gap = -5."""
    if not hub_path:
        return 0, ["hub_path not configured"]

    # Import and run parity check inline
    sys.path.insert(0, str(spoke / "tools"))
    try:
        from spoke_parity_check import check_spoke
        result = check_spoke(spoke, hub_path, verbose=False)
        if "error" in result:
            return 5, [f"parity check error: {result['error']}"]
        gaps = result.get("gaps", [])
        score = max(0, 20 - len(gaps) * 5)
        notes = [f"gap: {g['patch']} — {g['detail']}" for g in gaps]
        return score, notes
    except ImportError:
        return 5, ["spoke_parity_check.py not found"]
    finally:
        sys.path.pop(0)


def score_hub(spoke: Path, hub_path: str) -> tuple[int, list[str]]:
    """Max 20 pts: hub reachable (10), teachings current (10)."""
    if not hub_path:
        return 0, ["hub_path not configured"]

    hub = Path(hub_path)
    score = 0
    notes = []

    # Hub reachable
    if hub.exists():
        score += 10
    else:
        notes.append(f"hub not found: {hub_path}")
        return score, notes

    # Teachings current (no unprocessed)
    teach_dir = hub / "teachings_repo" / "framework" / "current"
    processed_dir = _wai_base(spoke) / "seed" / "ingest" / "processed"
    if not teach_dir.exists():
        notes.append("teachings_repo/framework/current/ missing")
    else:
        unprocessed = 0
        for f in teach_dir.glob("*.teaching"):
            if not (processed_dir / f.name).exists():
                unprocessed += 1
        if unprocessed == 0:
            score += 10
        else:
            deduct = min(unprocessed * 2, 10)
            score += max(0, 10 - deduct)
            notes.append(f"{unprocessed} unprocessed teachings")

    return score, notes


def hook_freshness_check(spoke: Path, framework_dir: Path = None) -> dict:
    """Compare spoke .claude/hooks/ mtimes against framework canonical templates.

    Stale = canonical template is 14+ days newer than the spoke's copy.
    Returns {"stale": [{"name": str, "age_days": int}], "all_current": bool}
    """
    if framework_dir is None:
        framework_dir = Path(__file__).parent.parent

    canonical_dir = framework_dir / "templates" / "spoke" / ".claude" / "hooks"
    spoke_hooks_dir = spoke / ".claude" / "hooks"

    if not canonical_dir.exists() or not spoke_hooks_dir.exists():
        return {"stale": [], "all_current": True}

    threshold = 14 * 24 * 3600
    stale = []

    for canonical in canonical_dir.glob("*.sh"):
        spoke_hook = spoke_hooks_dir / canonical.name
        if not spoke_hook.exists():
            continue
        age_seconds = canonical.stat().st_mtime - spoke_hook.stat().st_mtime
        if age_seconds > threshold:
            stale.append({"name": canonical.name, "age_days": int(age_seconds / 86400)})

    stale.sort(key=lambda x: -x["age_days"])
    return {"stale": stale, "all_current": len(stale) == 0}


def compute_score(spoke_path: str) -> dict:
    spoke = Path(spoke_path).resolve()

    # Load hub path from state (harness-mode-aware: reads from the active tree)
    hub_path = ""
    state_file = _wai_base(spoke) / "WAI-State.json"
    if state_file.exists():
        try:
            with open(state_file) as f:
                state = json.load(f)
            hub_path = state.get("wheel", {}).get("hub_path", "")
        except (json.JSONDecodeError, OSError):
            pass

    dims = {}
    s1, n1 = score_structure(spoke)
    s2, n2 = score_hooks(spoke)
    s3, n3 = score_lugs(spoke)
    s4, n4 = score_parity(spoke, hub_path)
    s5, n5 = score_hub(spoke, hub_path)

    dims = {
        "structure": {"score": s1, "max": 20, "notes": n1},
        "hooks":     {"score": s2, "max": 20, "notes": n2},
        "lugs":      {"score": s3, "max": 20, "notes": n3},
        "parity":    {"score": s4, "max": 20, "notes": n4},
        "hub":       {"score": s5, "max": 20, "notes": n5},
    }

    total = s1 + s2 + s3 + s4 + s5
    grade = "healthy" if total >= 80 else ("degraded" if total >= 50 else "critical")

    return {
        "spoke": str(spoke),
        "score": total,
        "max": 100,
        "grade": grade,
        "dimensions": dims,
    }


def print_report(result: dict):
    score = result["score"]
    grade = result["grade"]
    icon = "✓" if grade == "healthy" else ("⚠" if grade == "degraded" else "✗")

    print(f"Integrity Score: {score}/100  [{icon} {grade.upper()}]")
    print(f"Spoke: {result['spoke']}")
    print()
    for dim, data in result["dimensions"].items():
        s, m = data["score"], data["max"]
        bar = "█" * (s * 5 // m) + "░" * (5 - s * 5 // m)
        print(f"  {dim:<10} {bar}  {s:>2}/{m}")
        for note in data["notes"]:
            print(f"              ↳ {note}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Compute spoke integrity score (0-100)")
    parser.add_argument("spoke_path", nargs="?", default=".", help="Path to spoke (default: .)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--quiet", action="store_true", help="Score only (no report)")
    args = parser.parse_args()

    result = compute_score(args.spoke_path)

    if args.json:
        print(json.dumps(result, indent=2))
    elif args.quiet:
        print(result["score"])
    else:
        print_report(result)

    score = result["score"]
    if score >= 80:
        sys.exit(0)
    elif score >= 50:
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
