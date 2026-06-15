#!/usr/bin/env python3
"""
generate_ozi_brief.py — Generate ozi-brief.json with self-validation.

Builder-Validator Pattern:
1. BUILD: Collect brief data
2. CHECK: Validate against schema + live scan
3. REPAIR: If validation fails, log refinement and retry once
4. Output: brief + validation status

Usage:
    python3 tools/generate_ozi_brief.py
    python3 tools/generate_ozi_brief.py --skip-validation  # trust blindly
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wai_paths  # noqa: E402  harness-mode root resolver


def resolve_spoke_path(root: str, mode: str = None):
    """Return (base_path, advisors_path) for the active harness rooted at *root*.

    base_path    — working-state base (v3: <root>/WAI-Spoke ;
                   v4: <root>/WAI-Harness/spoke/local).
    advisors_path — sibling advisors dir (v3: <base>/advisors ;
                    v4: <root>/WAI-Harness/spoke/advisors — NOT under local/).

    Falls back to the legacy WAI-Spoke path when neither tree is present so that
    existing callers that run outside a live spoke still behave as before.
    """
    base, active = wai_paths.resolve_wai_root(root, mode)
    if base is None:
        # No harness tree present — fall back to legacy WAI-Spoke layout.
        fallback = Path(root) / "WAI-Spoke"
        return fallback, fallback / "advisors"
    base_p = Path(base)
    adv_p = Path(wai_paths.advisors_dir(root, mode) or (base_p / "advisors"))
    return base_p, adv_p


# Resolve the spoke root: prefer CWD if it has a WAI harness tree, else fall
# back to the repo root two levels above this file (the historical default).
_root = (
    str(Path.cwd())
    if (
        (Path.cwd() / "WAI-Spoke").exists()
        or (Path.cwd() / "WAI-Harness").exists()
    )
    else str(Path(__file__).parent.parent)
)
SPOKE_PATH, _ADVISORS_PATH = resolve_spoke_path(_root)

BRIEF_PATH = SPOKE_PATH / "ozi-brief.json"
REFINEMENTS_PATH = _ADVISORS_PATH / "ozi" / "refinements.jsonl"
SCAN_STATE_PATH = _ADVISORS_PATH / "ozi" / "scan_state.json"
TOLERANCE = 0.05


def collect_lug_counts() -> Dict[str, int]:
    lugs_dir = SPOKE_PATH / "lugs" / "bytype"

    open_count = 0
    in_progress_count = 0

    if not lugs_dir.exists():
        return {"open": 0, "in_progress": 0, "undelivered_signals": 0}

    for type_dir in lugs_dir.iterdir():
        if not type_dir.is_dir():
            continue

        open_dir = type_dir / "open"
        in_progress_dir = type_dir / "in_progress"

        if open_dir.exists():
            open_count += len(list(open_dir.glob("*.json")))
        if in_progress_dir.exists():
            in_progress_count += len(list(in_progress_dir.glob("*.json")))

    signal_dir = lugs_dir / "signal" / "undelivered"
    undelivered = len(list(signal_dir.glob("*.json"))) if signal_dir.exists() else 0

    return {
        "open": open_count,
        "in_progress": in_progress_count,
        "undelivered_signals": undelivered,
    }


def collect_teaching_status() -> Dict[str, int]:
    seed_dir = SPOKE_PATH / "seed"
    pending_dir = seed_dir / "ingest"
    processed_dir = seed_dir / "processed"

    pending = len(list(pending_dir.glob("*.md"))) if pending_dir.exists() else 0
    adopted = len(list(processed_dir.glob("*.md"))) if processed_dir.exists() else 0

    return {"pending": pending, "adopted": adopted}


def collect_expediter_stats() -> Dict[str, Any]:
    expediter_state_path = _ADVISORS_PATH / "expediter" / "scan_state.json"

    if not expediter_state_path.exists():
        return {"avg_quality": 0, "needs_refinement": 0, "teaching_candidates": 0}

    with open(expediter_state_path) as f:
        state = json.load(f)

    stats = state.get("stats", {})
    return {
        "avg_quality": stats.get("last_quality_avg", 0),
        "needs_refinement": stats.get("last_needs_refinement", 0),
        "teaching_candidates": stats.get("teaching_candidates_found", 0),
    }


def collect_session_summary() -> tuple:
    state_path = SPOKE_PATH / "WAI-State.json"

    if not state_path.exists():
        return "No previous session", "Run /wai to initialize"

    with open(state_path) as f:
        state = json.load(f)

    session_state = state.get("_session_state", {})
    last_summary = session_state.get("last_session_summary", "No summary available")
    next_rec = session_state.get("next_session_recommendation", "No recommendation")

    return last_summary, next_rec


def collect_tool_advisor_status() -> Dict[str, Any]:
    state_path = _ADVISORS_PATH / "tool-advisor" / "scan_state.json"
    if not state_path.exists():
        return {
            "audit_pending": True,
            "audit_reason": "tool-advisor state missing",
            "current_score": 0,
        }

    with open(state_path) as f:
        state = json.load(f)

    return {
        "audit_pending": bool(state.get("audit_pending", False)),
        "audit_reason": state.get("audit_reason", ""),
        "current_score": int(state.get("current_score", 0)),
    }


def validate_brief(brief: Dict[str, Any]) -> Dict[str, Any]:
    issues = []

    required = [
        ("generated_at", str),
        ("session_id", str),
        ("lug_queue.open", int),
        ("lug_queue.in_progress", int),
        ("lug_queue.undelivered_signals", int),
        ("teaching_status.pending", int),
        ("teaching_status.adopted", int),
        ("expediter.avg_quality", (int, float)),
        ("expediter.needs_refinement", int),
        ("expediter.teaching_candidates", int),
        ("last_session_summary", str),
        ("next_recommendation", str),
        ("tool_advisor.audit_pending", bool),
        ("tool_advisor.audit_reason", str),
        ("tool_advisor.current_score", int),
    ]

    for field_path, expected_type in required:
        parts = field_path.split(".")
        value = brief
        try:
            for part in parts:
                value = value[part]
            if not isinstance(value, expected_type):
                issues.append(
                    {
                        "rule": "Rule 1",
                        "field": field_path,
                        "issue": f"Wrong type: expected {expected_type}, got {type(value).__name__}",
                        "evidence": f"Value: {value}",
                    }
                )
        except KeyError:
            issues.append(
                {
                    "rule": "Rule 1",
                    "field": field_path,
                    "issue": "Missing required field",
                    "evidence": "Field not found",
                }
            )

    live_lug_counts = collect_lug_counts()
    for field in ["open", "in_progress"]:
        brief_val = brief["lug_queue"][field]
        live_val = live_lug_counts[field]

        if live_val > 0:
            delta = abs(brief_val - live_val) / live_val
            if delta > TOLERANCE:
                issues.append(
                    {
                        "rule": "Rule 2",
                        "field": f"lug_queue.{field}",
                        "brief_value": brief_val,
                        "live_value": live_val,
                        "delta": f"{delta * 100:.1f}%",
                        "evidence": f"Delta exceeds {TOLERANCE * 100}% tolerance",
                    }
                )

    generated_at = datetime.fromisoformat(brief["generated_at"].replace("Z", "+00:00"))
    age_seconds = (datetime.now(timezone.utc) - generated_at).total_seconds()
    if age_seconds > 60:
        issues.append(
            {
                "rule": "Rule 3",
                "field": "generated_at",
                "issue": "Stale timestamp",
                "evidence": f"Age: {age_seconds:.0f}s (> 60s)",
            }
        )

    expediter_stats = collect_expediter_stats()
    if brief["expediter"]["avg_quality"] != expediter_stats["avg_quality"]:
        issues.append(
            {
                "rule": "Rule 4",
                "field": "expediter.avg_quality",
                "brief_value": brief["expediter"]["avg_quality"],
                "scan_state_value": expediter_stats["avg_quality"],
                "evidence": "Mismatch with scan_state.json",
            }
        )

    teaching_status = collect_teaching_status()
    if teaching_status["adopted"] > 0 and brief["teaching_status"]["adopted"] == 0:
        issues.append(
            {
                "rule": "Rule 5",
                "field": "teaching_status.adopted",
                "brief_value": 0,
                "live_value": teaching_status["adopted"],
                "evidence": "Zero adopted but teachings exist in processed/",
            }
        )

    return {"passed": len(issues) == 0, "issues": issues}


def log_refinement_proposal(issue: Dict[str, Any], brief: Dict[str, Any]):
    REFINEMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    refinement = {
        "id": f"ref-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "advisor_id": "ozi",
        "target_area": "brief_collection",
        "collection_step": issue.get("field", "unknown"),
        "prior_behavior": "Current collection logic",
        "issue_detected": issue.get(
            "issue", issue.get("evidence", "Validation failed")
        ),
        "proposed_adjustment": f"Fix {issue.get('field', 'unknown')} collection",
        "evidence": json.dumps(issue),
        "expected_benefit": "Pass validation",
        "scope": "local",
        "promotion_status": "pending",
        "occurrences": 1,
        "failure_count": 0,
        "first_seen": datetime.now(timezone.utc).isoformat(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
    }

    with open(REFINEMENTS_PATH, "a") as f:
        f.write(json.dumps(refinement) + "\n")

    print(f"  📝 Refinement logged: {refinement['id']}")


def update_scan_state(validation_result: Dict[str, Any]):
    if not SCAN_STATE_PATH.exists():
        return

    with open(SCAN_STATE_PATH) as f:
        state = json.load(f)

    brief_gen = state.setdefault(
        "brief_generation",
        {
            "runs": 0,
            "validations_passed": 0,
            "validations_failed": 0,
            "refinements_pending": 0,
            "refinements_promoted": 0,
            "last_validation_passed": None,
            "last_validation_issues": [],
            "recent_failures": [],
        },
    )

    brief_gen["runs"] += 1

    if validation_result["passed"]:
        brief_gen["validations_passed"] += 1
        brief_gen["last_validation_passed"] = True
        brief_gen["last_validation_issues"] = []
    else:
        brief_gen["validations_failed"] += 1
        brief_gen["last_validation_passed"] = False
        brief_gen["last_validation_issues"] = validation_result["issues"]

        recent = brief_gen["recent_failures"]
        recent.append(datetime.now(timezone.utc).isoformat())
        brief_gen["recent_failures"] = recent[-10:]

        if len(recent) > 3:
            print(f"  ⚠️  ESCALATION: {len(recent)} validation failures in recent runs")
            print(f"     Root cause review recommended")

    if REFINEMENTS_PATH.exists():
        with open(REFINEMENTS_PATH) as f:
            pending = sum(
                1
                for line in f
                if line.strip()
                and json.loads(line).get("promotion_status") == "pending"
            )
            brief_gen["refinements_pending"] = pending

    with open(SCAN_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def generate_brief(skip_validation: bool = False) -> Dict[str, Any]:
    state_path = SPOKE_PATH / "WAI-State.json"
    session_id = "unknown"
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)
            session_id = state.get("_session_state", {}).get(
                "current_session", "unknown"
            )

    brief = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "lug_queue": collect_lug_counts(),
        "teaching_status": collect_teaching_status(),
        "expediter": collect_expediter_stats(),
        "last_session_summary": "",
        "next_recommendation": "",
        "tool_advisor": collect_tool_advisor_status(),
    }

    brief["last_session_summary"], brief["next_recommendation"] = (
        collect_session_summary()
    )

    print(f"  Brief collected: {brief['lug_queue']}")

    if not skip_validation:
        validation = validate_brief(brief)

        if not validation["passed"]:
            print(f"  ❌ Validation failed: {len(validation['issues'])} issues")

            for issue in validation["issues"]:
                log_refinement_proposal(issue, brief)

            print("  Retrying with fresh collection...")
            brief["lug_queue"] = collect_lug_counts()
            brief["teaching_status"] = collect_teaching_status()
            brief["expediter"] = collect_expediter_stats()

            validation2 = validate_brief(brief)
            if not validation2["passed"]:
                print(f"  ❌ Validation still failed after retry")

            update_scan_state(validation)
        else:
            print(f"  ✅ Validation passed")
            update_scan_state(validation)
    else:
        print(f"  ⏭️  Validation skipped")

    with open(BRIEF_PATH, "w") as f:
        json.dump(brief, f, indent=2)

    print(f"  💾 Brief saved: {BRIEF_PATH}")
    return brief


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate ozi-brief.json")
    parser.add_argument(
        "--skip-validation", action="store_true", help="Skip validation checks"
    )
    args = parser.parse_args()

    print("Ozi Brief Generator")
    print("=" * 50)
    generate_brief(skip_validation=args.skip_validation)
