#!/usr/bin/env python3
"""
advisor_schedule_eval.py — Evaluate which advisors should fire this session.

Reads advisors/schedule-index.json (location resolved via wai_paths — v3 or v4
depending on $WAI_HARNESS_MODE), compares last_run_at + run_cadence against current
time, and checks event_triggers against current spoke state.

Output: JSON array of {advisor_id, should_fire, reason}

Usage:
    python3 tools/advisor_schedule_eval.py
    python3 tools/advisor_schedule_eval.py --json   # machine-readable only

In v4-only mode ($WAI_HARNESS_MODE=v4-only) all paths resolve to the v4 tree
(WAI-Harness/spoke/local + WAI-Harness/spoke/advisors); WAI-Spoke is never touched.
"""

import argparse
import json
import subprocess
import sys
import datetime
import os
from pathlib import Path
import logging

# wai_paths is the single resolver for harness-mode-aware paths.
# Import it here; the module may live next to this file (tools/) or on sys.path.
try:
    import wai_paths as _wai_paths
except ImportError:
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _this_dir)
    import wai_paths as _wai_paths

logging.basicConfig(
    level=logging.INFO,
    format="[advisor_schedule_eval] %(levelname)s: %(message)s"
)

# ------------------------------------------------------------------
# Legacy module-level path constants — DEPRECATED; kept only as a
# last-resort fallback when no spoke_root is available (e.g. direct
# __main__ invocation from an unknown cwd).  All internal callers
# now go through _resolve_paths(spoke_root) instead.
# ------------------------------------------------------------------
_LEGACY_SCHEDULE_INDEX = "WAI-Spoke/advisors/schedule-index.json"
_LEGACY_WAI_STATE = "WAI-Spoke/WAI-State.json"
_LEGACY_TOOL_ADVISOR_STATE = "WAI-Spoke/advisors/tool-advisor/scan_state.json"


def _resolve_paths(spoke_root=None):
    """Return a dict of harness-mode-aware absolute paths for this spoke.

    Keys: schedule_index, wai_state, tool_advisor_state, db_supabase, vendors

    When WAI_HARNESS_MODE=v4-only the paths point into the v4 tree
    (WAI-Harness/spoke/local / WAI-Harness/spoke/advisors); otherwise they fall
    back to the v3 WAI-Spoke layout.  Both modes preserve the same semantics so
    callers are mode-agnostic.
    """
    root = os.path.abspath(spoke_root) if spoke_root else os.path.abspath(".")
    base, _mode = _wai_paths.resolve_wai_root(root)
    adv = _wai_paths.advisors_dir(root)

    if base is None:
        # No harness tree present — fall back to legacy relative paths so the
        # tool degrades gracefully (e.g. "schedule-index not found" error path).
        return {
            "schedule_index": _LEGACY_SCHEDULE_INDEX,
            "wai_state": _LEGACY_WAI_STATE,
            "tool_advisor_state": _LEGACY_TOOL_ADVISOR_STATE,
            "db_supabase": os.path.join("WAI-Spoke", "db", "supabase"),
            "vendors": os.path.join("WAI-Spoke", "vendors.json"),
        }

    return {
        "schedule_index": os.path.join(adv, "schedule-index.json"),
        "wai_state": os.path.join(base, "WAI-State.json"),
        "tool_advisor_state": os.path.join(adv, "tool-advisor", "scan_state.json"),
        "db_supabase": os.path.join(base, "db", "supabase"),
        "vendors": os.path.join(base, "vendors.json"),
    }

CADENCE_DAYS = {
    "daily": 1,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "never": None,
}

SUPABASE_KEYWORDS = {"supabase", "postgres", "pgsql", "rls"}
TEACHING_SUBSTRATE_MARKERS = {
    "supabase": ["supabase", "rls", "row level security"],
}


def load_spoke_state(spoke_root=None):
    wai_state = _resolve_paths(spoke_root)["wai_state"]
    try:
        return json.load(open(wai_state))
    except Exception:
        return {}


def detect_teaching_substrate(teaching: dict | str) -> str | None:
    """Detect required substrate from teaching metadata.

    Returns the substrate name (e.g. 'supabase') if the teaching is substrate-specific,
    else None. Checks:
    - db_substrate field in metadata
    - tags/keywords field
    - 'Affects' line in description
    - Title/content keywords
    """
    if isinstance(teaching, str):
        content = teaching
    else:
        content = str(teaching.get("content", "")) + " " + str(teaching.get("description", ""))

    content_lower = content.lower()
    for substrate, keywords in TEACHING_SUBSTRATE_MARKERS.items():
        if any(kw in content_lower for kw in keywords):
            return substrate
    return None


def spoke_has_substrate(spoke_path: str | None, substrate: str) -> bool:
    """Check if a spoke has the given substrate installed/configured.

    Looks for:
    - db_substrate field in hub-registry entry (if available)
    - vendor entries in spoke config
    - presence of substrate-specific directories/files
    """
    if not spoke_path:
        return False

    spoke_path = Path(spoke_path)

    if substrate == "supabase":
        # Resolve the harness-mode-aware db/supabase path for this spoke.
        p = _resolve_paths(str(spoke_path))
        wai_db_supabase = Path(p["db_supabase"])
        return (spoke_path / "supabase").exists() or \
               wai_db_supabase.exists() or \
               _vendor_has_supabase(spoke_path)

    return False


def _vendor_has_supabase(spoke_path: Path) -> bool:
    """Check if spoke's vendor config mentions Supabase."""
    # Resolve the harness-mode-aware vendors.json path for this spoke.
    p = _resolve_paths(str(spoke_path))
    vendors_paths = [
        spoke_path / "secrets" / "vendors.json",
        Path(p["vendors"]),
    ]
    for vpath in vendors_paths:
        if vpath.exists():
            try:
                data = json.loads(vpath.read_text())
                vendors = data.get("vendors", [])
                if isinstance(vendors, dict):
                    vendors = list(vendors.keys())
                if "supabase" in [v.lower() for v in vendors]:
                    return True
            except (OSError, json.JSONDecodeError):
                pass
    return False


def _feat_commits_since(last_run_at: str | None) -> bool:
    """Return True if any feat(*) commit landed since last_run_at.

    Uses ``git log --since`` with a ``--grep`` filter.  Any subprocess failure
    (git not found, non-git directory, timeout) returns False silently so the
    caller never raises.
    """
    if not last_run_at:
        return False
    try:
        result = subprocess.run(
            ["git", "log", f"--since={last_run_at}", "--oneline", "--grep=feat("],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def _teaching_retired_since(last_run_at: str | None) -> bool:
    """Return True if any retirement/deprecation commit landed since last_run_at.

    Matches commits whose message contains ``retirement``, ``deprecat``, or
    ``retired``.  Subprocess failures return False silently.
    """
    if not last_run_at:
        return False
    try:
        result = subprocess.run(
            [
                "git", "log", f"--since={last_run_at}", "--oneline",
                "--grep=retirement", "--grep=deprecat", "--grep=retired",
                "--regexp-ignore-case",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except Exception:
        return False


def stage_teaching_to_spoke(teaching: dict, spoke_id: str, spoke_path: str | None) -> tuple[bool, str]:
    """Evaluate whether a teaching should be delivered to a spoke.

    Returns (should_deliver, reason). Reason is logged if should_deliver is False.
    """
    teaching_id = teaching.get("id", teaching.get("name", "unknown"))
    required_substrate = detect_teaching_substrate(teaching)

    if not required_substrate:
        return True, "no substrate requirements"

    if not spoke_path:
        return False, f"spoke_path not provided for {spoke_id}"

    if spoke_has_substrate(spoke_path, required_substrate):
        return True, f"spoke has {required_substrate}"

    return False, f"teaching requires {required_substrate}, spoke {spoke_id} has no {required_substrate}"


def check_event_triggers(triggers: list, state: dict, last_run_at: str | None = None) -> str | None:
    """Return trigger reason if any event trigger is active, else None."""
    wq = state.get("_work_queue", {})
    items = wq.get("items", [])
    open_count = len([i for i in items if i.get("status") == "ready"])

    trigger_map = {
        "lug_created": open_count > 0,
        "lug_updated": open_count > 0,
        "open_lugs_exceed_10": open_count > 10,
        "release_candidate_exists": False,  # extend as needed
        "deploy_gate_triggered": False,
        "specialist_run_completed": False,
        # Git-based event triggers (require last_run_at to detect new activity)
        "feat_commit_since_last_run": _feat_commits_since(last_run_at),
        "teaching_retired_since_last_run": _teaching_retired_since(last_run_at),
    }

    for trigger in triggers:
        if trigger_map.get(trigger, False):
            return f"event trigger: {trigger}"
    return None


def check_subordinates_complete(subordinates: list, index: list, now: datetime.datetime) -> tuple[bool, str]:
    """Return (all_complete, reason) for after_subordinates trigger evaluation."""
    if not subordinates:
        return True, "no subordinates configured"
    index_by_id = {e["advisor_id"]: e for e in index if not e.get("trigger")}
    incomplete = []
    for sub_id in subordinates:
        sub = index_by_id.get(sub_id)
        if not sub:
            incomplete.append(f"{sub_id} (not in index)")
            continue
        last_run_str = sub.get("last_run_at")
        if not last_run_str:
            incomplete.append(f"{sub_id} (never run)")
            continue
        try:
            last_run = datetime.datetime.fromisoformat(last_run_str.replace("Z", "+00:00"))
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=datetime.timezone.utc)
            cadence_key = sub.get("run_cadence") or "weekly"
            days = CADENCE_DAYS.get(cadence_key, 7)
            if days and (now - last_run).days > days:
                incomplete.append(f"{sub_id} (stale: {(now - last_run).days}d)")
        except Exception:
            incomplete.append(f"{sub_id} (last_run_at parse error)")
    if incomplete:
        return False, ", ".join(incomplete)
    return True, "all subordinates have run within cadence"


def eval_advisor(entry: dict, now: datetime.datetime, state: dict, index: list | None = None, spoke_root=None) -> dict:
    advisor_id = entry["advisor_id"]
    cadence_key = entry.get("run_cadence") or "weekly"
    last_run_str = entry.get("last_run_at")
    triggers = entry.get("event_triggers") or []

    tool_advisor_state = _resolve_paths(spoke_root)["tool_advisor_state"]
    if advisor_id == "tool-advisor" and Path(tool_advisor_state).exists():
        try:
            tool_state = json.load(open(tool_advisor_state))
            if tool_state.get("audit_pending"):
                reason = tool_state.get("audit_reason") or "tool config drift"
                return {"advisor_id": advisor_id, "should_fire": True, "reason": reason}
        except Exception:
            return {"advisor_id": advisor_id, "should_fire": True, "reason": "tool-advisor state unreadable"}

    # Handle synthesis trigger — fires after all subordinate advisors have run
    if entry.get("trigger") == "after_subordinates":
        subs = entry.get("subordinates") or []
        all_done, reason = check_subordinates_complete(subs, index or [], now)
        if not all_done:
            return {"advisor_id": advisor_id, "should_fire": False, "reason": f"waiting for subordinates: {reason}"}
        last_run_str = entry.get("last_run_at")
        cadence_key = entry.get("cadence") or "weekly"
        days = CADENCE_DAYS.get(cadence_key, 7)
        if last_run_str and days:
            try:
                last_run = datetime.datetime.fromisoformat(last_run_str.replace("Z", "+00:00"))
                if last_run.tzinfo is None:
                    last_run = last_run.replace(tzinfo=datetime.timezone.utc)
                if (now - last_run).days < days:
                    elapsed = (now - last_run).days
                    return {"advisor_id": advisor_id, "should_fire": False, "reason": f"synthesis current ({elapsed}d ago)"}
            except Exception:
                pass
        return {"advisor_id": advisor_id, "should_fire": True, "reason": "synthesis due: all subordinates have run"}

    # Check event triggers first (pass last_run_at for git-based triggers)
    trigger_reason = check_event_triggers(triggers, state, last_run_at=last_run_str)
    if trigger_reason:
        return {"advisor_id": advisor_id, "should_fire": True, "reason": trigger_reason}

    # Check cadence
    days = CADENCE_DAYS.get(cadence_key)
    if days is None:
        return {"advisor_id": advisor_id, "should_fire": False, "reason": "cadence=never"}

    if last_run_str is None:
        return {"advisor_id": advisor_id, "should_fire": True, "reason": "never run"}

    try:
        last_run = datetime.datetime.fromisoformat(last_run_str.replace("Z", "+00:00"))
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=datetime.timezone.utc)
        elapsed = (now - last_run).days
        if elapsed >= days:
            return {
                "advisor_id": advisor_id,
                "should_fire": True,
                "reason": f"{elapsed}d since last run (cadence: {cadence_key})",
            }
        else:
            return {
                "advisor_id": advisor_id,
                "should_fire": False,
                "reason": f"{elapsed}d since last run, next in {days - elapsed}d",
            }
    except Exception as e:
        return {"advisor_id": advisor_id, "should_fire": True, "reason": f"parse error on last_run_at: {e}"}


def _eval_teaching_delivery(teachings_path: str, spokes_path: str | None, machine_only: bool):
    """Evaluate teaching delivery to spokes based on substrate compatibility."""
    teachings = []
    spokes = {}

    if teachings_path and Path(teachings_path).exists():
        try:
            data = json.loads(Path(teachings_path).read_text())
            if isinstance(data, dict):
                teachings = data.get("teachings", data.get("entries", []))
            elif isinstance(data, list):
                teachings = data
        except (json.JSONDecodeError, OSError) as e:
            logging.error(f"Failed to load teachings: {e}")
            print(json.dumps({"error": f"Failed to load teachings: {e}"}))
            sys.exit(1)

    if spokes_path and Path(spokes_path).exists():
        try:
            data = json.loads(Path(spokes_path).read_text())
            if isinstance(data, dict) and "wheels" in data:
                for wheel in data.get("wheels", []):
                    sid = wheel.get("spoke_id", wheel.get("wheel_id"))
                    spokes[sid] = wheel.get("path")
            else:
                for line in spokes_path.split(","):
                    line = line.strip()
                    if line:
                        spokes[Path(line).name] = line
        except (json.JSONDecodeError, OSError) as e:
            logging.error(f"Failed to load spokes: {e}")

    results = []
    for teaching in teachings:
        teaching_id = teaching.get("id", teaching.get("name", "unknown"))
        substrate = detect_teaching_substrate(teaching)

        if not substrate:
            logging.debug(f"Teaching {teaching_id}: no substrate requirements")
            continue

        for spoke_id, spoke_path in spokes.items():
            should_deliver, reason = stage_teaching_to_spoke(teaching, spoke_id, spoke_path)
            results.append({
                "teaching_id": teaching_id,
                "spoke_id": spoke_id,
                "should_deliver": should_deliver,
                "reason": reason,
                "substrate": substrate
            })
            if not should_deliver:
                logging.info(f"SKIP: teaching={teaching_id}, spoke={spoke_id}: {reason}")

    if machine_only:
        print(json.dumps(results))
    else:
        skipped = [r for r in results if not r["should_deliver"]]
        delivered = [r for r in results if r["should_deliver"]]

        if skipped:
            print(f"Teaching delivery skipped ({len(skipped)}):")
            for r in skipped:
                print(f"  {r['teaching_id']:30} → {r['spoke_id']:20} {r['reason']}")

        if delivered:
            print(f"\nTeaching delivery approved ({len(delivered)}):")
            for r in delivered:
                print(f"  {r['teaching_id']:30} → {r['spoke_id']:20} {r['reason']}")

        print(f"\n{json.dumps(results)}")

    return


def main():
    parser = argparse.ArgumentParser(description="Evaluate advisor schedule readiness and teaching delivery.")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output only")
    parser.add_argument("--verbose", action="store_true", help="Show advisors not yet scheduled")
    parser.add_argument("--teachings", type=str, help="Path to teachings index JSON or single teaching file")
    parser.add_argument("--spokes", type=str, help="Path to hub-registry.json or spoke paths (comma-separated)")
    parser.add_argument("--eval-teaching-delivery", action="store_true", help="Evaluate teaching delivery to spokes")
    parser.add_argument("--root", type=str, default=None, help="Spoke root directory (default: cwd); used for harness-mode path resolution")
    args = parser.parse_args()
    machine_only = args.json

    if args.eval_teaching_delivery and args.teachings:
        return _eval_teaching_delivery(args.teachings, args.spokes, machine_only)

    spoke_root = args.root  # None → cwd in _resolve_paths
    paths = _resolve_paths(spoke_root)
    schedule_index = paths["schedule_index"]

    if not os.path.exists(schedule_index):
        if not machine_only:
            print(f"schedule-index.json not found at {schedule_index}", file=sys.stderr)
        print("[]")
        sys.exit(0)

    index = json.load(open(schedule_index))
    state = load_spoke_state(spoke_root)
    now = datetime.datetime.now(datetime.timezone.utc)

    results = [eval_advisor(entry, now, state, index, spoke_root=spoke_root) for entry in index]

    if machine_only:
        print(json.dumps(results))
        return

    ready = [r for r in results if r["should_fire"]]
    not_ready = [r for r in results if not r["should_fire"]]

    if ready:
        print(f"Advisors ready to fire ({len(ready)}):")
        for r in ready:
            print(f"  {r['advisor_id']:20} {r['reason']}")
    else:
        print("No advisors scheduled to fire this session.")

    if not_ready and args.verbose:
        print(f"\nNot scheduled ({len(not_ready)}):")
        for r in not_ready:
            print(f"  {r['advisor_id']:20} {r['reason']}")

    # Always write machine-readable to stdout for hook consumption
    if not machine_only:
        print(f"\n{json.dumps(results)}")


if __name__ == "__main__":
    main()
