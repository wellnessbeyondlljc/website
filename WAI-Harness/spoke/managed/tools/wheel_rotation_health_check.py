#!/usr/bin/env python3
"""Wheel Rotation Health Check — verify the Navigator->AP->Hub loop closed.

Checks 6 timestamped checkpoints:
  V1 Navigator profile used and fresh (<48h)
  V2 teachings_adopted key present in AP log entry
  V3 Spoke completion event landed at hub after AP run
  V4 Hub advisory-refresh ran after completion event
  V5 Navigator recommendations regenerated after hub refresh
  V6 PathGraph trace written after AP run (advisory only)

Writes rotation-check-latest.json to WAI-Spoke/advisors/health/.
Creates bug lugs for failing core checkpoints (V1-V5).
Exits 0 if loop_closed (V1-V5 all pass), else exits 1.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Spoke-base resolution (base-aware)
# ---------------------------------------------------------------------------
# PRE-FIX every spoke-local path blindly appended "WAI-Spoke" -> on a v4-only spoke
# the whole rotation check read/wrote a nonexistent tree and silently no-op'd
# (impl-fix-p2-v3noop-sweep-v1). Working-state categories (WAI-State.json, sessions,
# lugs, pathgraph) live under the resolved base (WAI-Harness/spoke/local on v4);
# advisors are a SIBLING (WAI-Harness/spoke/advisors on v4) so they resolve via
# advisors_dir(). Hub paths (hub_path / "WAI-Spoke" / ...) are real and untouched.

def _spoke_base(spoke_path: Path) -> Path:
    """Working-state base for the spoke (lugs/sessions/state/pathgraph), base-aware."""
    try:
        from wai_paths import resolve_wai_root
        root, mode = resolve_wai_root(str(spoke_path))
        if root and mode != "none":
            return Path(root)
    except Exception:
        pass
    return Path(spoke_path) / "WAI-Spoke"  # last-resort v3 fallback


def _advisors_base(spoke_path: Path) -> Path:
    """Advisors live beside the working base, not under it (v4: WAI-Harness/spoke/advisors)."""
    try:
        from wai_paths import advisors_dir
        adv = advisors_dir(str(spoke_path))
        if adv:
            return Path(adv)
    except Exception:
        pass
    return Path(spoke_path) / "WAI-Spoke" / "advisors"  # last-resort v3 fallback


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_iso(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string to an aware UTC datetime, or None."""
    if not ts_str:
        return None
    try:
        clean = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now_utc().isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# AP log discovery
# ---------------------------------------------------------------------------

def _find_ap_log(spoke_path: Path, ap_log_override: Optional[str]) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    """Locate and return the most recent AP run entry.

    Search order:
    1. --ap-log override if provided
    2. WAI-Spoke/advisors/autopilot/activity-log.jsonl — last non-empty line
    3. Glob WAI-Spoke/sessions/*/autopilot-summary.json — newest mtime
    4. WAI-Spoke/advisors/autopilot/scan_state.json last_run_at as fallback stub

    Returns (path, entry_dict) or (None, None).
    """
    # 1. Explicit override
    if ap_log_override:
        p = Path(ap_log_override)
        if p.exists():
            try:
                raw = p.read_text(encoding="utf-8").strip().splitlines()
                for line in reversed(raw):
                    line = line.strip()
                    if line:
                        return p, json.loads(line)
            except (OSError, json.JSONDecodeError):
                pass
        return None, None

    # 2. activity-log.jsonl — last non-empty line
    activity_log = _advisors_base(spoke_path) / "autopilot" / "activity-log.jsonl"
    if activity_log.exists():
        try:
            raw = activity_log.read_text(encoding="utf-8").strip().splitlines()
            for line in reversed(raw):
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if "lug_id" in entry:
                            continue
                        return activity_log, entry
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

    # 3. Glob sessions/*/autopilot-summary.json — newest mtime
    session_pattern = _spoke_base(spoke_path) / "sessions"
    if session_pattern.exists():
        candidates = list(session_pattern.glob("*/autopilot-summary.json"))
        if candidates:
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            try:
                return candidates[0], json.loads(candidates[0].read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

    # 4. scan_state.json last_run_at as minimal stub
    scan_state = _advisors_base(spoke_path) / "autopilot" / "scan_state.json"
    if scan_state.exists():
        try:
            data = json.loads(scan_state.read_text(encoding="utf-8"))
            last_run_at = data.get("last_run_at")
            if last_run_at:
                summary = data.get("last_run_summary", {})
                stub = {
                    "run_at": last_run_at,
                    "teachings_adopted": summary.get("teachings_adopted", 0),
                    "_source": "scan_state_stub",
                }
                return scan_state, stub
        except (OSError, json.JSONDecodeError):
            pass

    return None, None


# ---------------------------------------------------------------------------
# Hub path resolution
# ---------------------------------------------------------------------------

def _resolve_hub_path(spoke_path: Path, hub_path_arg: Optional[str]) -> Optional[Path]:
    """Return hub path from argument or from WAI-State.json wheel.hub_path."""
    if hub_path_arg:
        return Path(hub_path_arg)
    state_file = _spoke_base(spoke_path) / "WAI-State.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            hub_path_str = state.get("wheel", {}).get("hub_path")
            if hub_path_str:
                return Path(hub_path_str)
        except (OSError, json.JSONDecodeError):
            pass
    return None


def _get_spoke_id(spoke_path: Path) -> str:
    """Read wheel.spoke_id from WAI-State.json, fallback to 'unknown'."""
    state_file = _spoke_base(spoke_path) / "WAI-State.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            spoke_id = (
                state.get("wheel", {}).get("spoke_id")
                or state.get("wheel_id")
                or "unknown"
            )
            return str(spoke_id)
        except (OSError, json.JSONDecodeError):
            pass
    return "unknown"


# ---------------------------------------------------------------------------
# Checkpoint functions
# ---------------------------------------------------------------------------

def check_V1(ap_entry: Dict[str, Any], spoke_path: Path) -> Tuple[bool, str]:
    """V1: navigator_profile_used is identifiable AND recommendations-current.json exists (<48h).

    The activity-log.jsonl does not store navigator_profile_used as a top-level key.
    We check: (a) recommendations-current.json exists at all, and (b) generated_at is within 48h.
    A present recommendations file means the navigator ran before this AP run.
    """
    nav_file = _advisors_base(spoke_path) / "navigator" / "recommendations-current.json"
    if not nav_file.exists():
        return False, "recommendations-current.json not found in advisors/navigator/"

    try:
        nav_data = json.loads(nav_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Cannot read recommendations-current.json: {exc}"

    generated_at_str = nav_data.get("generated_at")
    generated_at = _parse_iso(generated_at_str)
    if generated_at is None:
        return False, f"recommendations-current.json missing or unparseable generated_at: {generated_at_str!r}"

    age = _now_utc() - generated_at
    if age > timedelta(hours=48):
        age_h = round(age.total_seconds() / 3600, 1)
        return False, f"recommendations-current.json is stale: generated_at={generated_at_str} ({age_h}h ago, limit 48h)"

    return True, f"Navigator profile present and fresh (generated_at={generated_at_str})"


def check_V2(ap_entry: Dict[str, Any]) -> Tuple[bool, str]:
    """V2: teachings_adopted key is present in AP log entry (0 is OK; absence means stub active)."""
    if "teachings_adopted" in ap_entry:
        count = ap_entry["teachings_adopted"]
        return True, f"teachings_adopted key present (value={count})"
    return False, "teachings_adopted key absent from AP log entry — entry may be a stub or from old AP version"


def check_V3(ap_entry: Dict[str, Any], hub_path: Optional[Path], spoke_id: str) -> Tuple[bool, str]:
    """V3: spoke-completion-event exists at hub with completed_at >= AP run start_ts AND matching spoke_id."""
    if hub_path is None:
        return False, "hub_path not available — cannot check spoke-completion-events"

    start_ts_str = ap_entry.get("run_at") or ap_entry.get("start_ts") or ap_entry.get("completed_at")
    start_ts = _parse_iso(start_ts_str)

    events_dir = hub_path / "WAI-Spoke" / "advisors" / "gardener" / "spoke-completion-events"
    if not events_dir.exists():
        return False, f"spoke-completion-events directory not found at {events_dir}"

    # Search unprocessed + processed sub-directories
    search_dirs = [events_dir]
    processed_sub = events_dir / "processed"
    if processed_sub.exists():
        search_dirs.append(processed_sub)

    found_any_spoke = False
    best_ts: Optional[str] = None

    for search_dir in search_dirs:
        for event_file in sorted(search_dir.glob("*.json")):
            try:
                event = json.loads(event_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            event_spoke = str(event.get("spoke_id", ""))
            if event_spoke != spoke_id:
                continue
            found_any_spoke = True

            completed_at_str = event.get("completed_at")
            completed_at = _parse_iso(completed_at_str)
            if completed_at is None:
                continue
            if start_ts is None or completed_at >= start_ts:
                best_ts = completed_at_str
                return True, f"Spoke completion event found: spoke_id={spoke_id}, completed_at={best_ts}"

    if found_any_spoke:
        return False, (
            f"Spoke completion events exist for spoke_id={spoke_id} but none have "
            f"completed_at >= AP start_ts={start_ts_str}"
        )
    return False, (
        f"No spoke completion events found for spoke_id={spoke_id} in {events_dir}"
    )


def check_V4(ap_entry: Dict[str, Any], hub_path: Optional[Path]) -> Tuple[bool, Optional[str]]:
    """V4: advisory-refresh-log.jsonl has an entry with processed_at >= AP start_ts.

    Returns (passed, refresh_ts_str_or_None).
    """
    if hub_path is None:
        return False, None

    start_ts_str = ap_entry.get("run_at") or ap_entry.get("start_ts") or ap_entry.get("completed_at")
    start_ts = _parse_iso(start_ts_str)

    # Hub stores log at WAI-Hub/advisors/gardener/advisory-refresh-log.jsonl
    # (process_completion_events.py path: WAI-Spoke/advisors/gardener/ in hub root)
    candidate_paths = [
        hub_path / "WAI-Hub" / "advisors" / "gardener" / "advisory-refresh-log.jsonl",
        hub_path / "WAI-Spoke" / "advisors" / "gardener" / "advisory-refresh-log.jsonl",
    ]

    log_path: Optional[Path] = None
    for p in candidate_paths:
        if p.exists():
            log_path = p
            break

    if log_path is None:
        return False, None

    try:
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return False, None

    # Scan from newest (last lines first)
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Field may be processed_at or run_at depending on version
        refresh_ts_str = entry.get("processed_at") or entry.get("run_at")
        refresh_ts = _parse_iso(refresh_ts_str)
        if refresh_ts is None:
            continue

        if start_ts is None or refresh_ts >= start_ts:
            return True, refresh_ts_str

    return False, None


def check_V4_detail(ap_entry: Dict[str, Any], hub_path: Optional[Path]) -> Tuple[bool, str]:
    """V4 with human-readable detail string."""
    start_ts_str = ap_entry.get("run_at") or ap_entry.get("start_ts") or ""
    passed, refresh_ts = check_V4(ap_entry, hub_path)
    if passed:
        return True, f"Hub advisory refresh ran at {refresh_ts} (after AP start {start_ts_str})"
    if hub_path is None:
        return False, "hub_path not available"
    log_candidates = [
        hub_path / "WAI-Hub" / "advisors" / "gardener" / "advisory-refresh-log.jsonl",
        hub_path / "WAI-Spoke" / "advisors" / "gardener" / "advisory-refresh-log.jsonl",
    ]
    for p in log_candidates:
        if p.exists():
            return False, (
                f"advisory-refresh-log.jsonl exists at {p} but no entry with "
                f"processed_at/run_at >= AP start_ts={start_ts_str}"
            )
    return False, f"advisory-refresh-log.jsonl not found (checked: {[str(p) for p in log_candidates]})"


def check_V5(spoke_path: Path, v4_refresh_ts_str: Optional[str]) -> Tuple[bool, str]:
    """V5: recommendations-current.json generated_at > hub refresh timestamp."""
    nav_file = _advisors_base(spoke_path) / "navigator" / "recommendations-current.json"
    if not nav_file.exists():
        return False, "recommendations-current.json not found"

    try:
        nav_data = json.loads(nav_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Cannot read recommendations-current.json: {exc}"

    nav_ts_str = nav_data.get("generated_at")
    nav_ts = _parse_iso(nav_ts_str)

    if v4_refresh_ts_str is None:
        return False, "V4 hub refresh timestamp unavailable — cannot verify V5"

    v4_ts = _parse_iso(v4_refresh_ts_str)

    if nav_ts is None:
        return False, f"recommendations-current.json has unparseable generated_at: {nav_ts_str!r}"

    if v4_ts is None:
        return False, f"V4 hub refresh timestamp is unparseable: {v4_refresh_ts_str!r}"

    if nav_ts >= v4_ts:
        return True, (
            f"Navigator ran AFTER hub refresh: nav generated_at={nav_ts_str}, "
            f"hub refresh={v4_refresh_ts_str}"
        )

    return False, (
        f"Navigator ran BEFORE hub refresh: nav generated_at={nav_ts_str}, "
        f"hub refresh={v4_refresh_ts_str} — navigator profile is stale relative to hub"
    )


def check_V6(ap_entry: Dict[str, Any], spoke_path: Path) -> Tuple[bool, str]:
    """V6 (advisory): pathgraph/history.jsonl has an entry with ts >= AP start_ts."""
    start_ts_str = ap_entry.get("run_at") or ap_entry.get("start_ts") or ap_entry.get("completed_at")
    start_ts = _parse_iso(start_ts_str)

    history_file = _spoke_base(spoke_path) / "pathgraph" / "history.jsonl"
    if not history_file.exists():
        return False, f"pathgraph/history.jsonl not found at {history_file}"

    try:
        lines = history_file.read_text(encoding="utf-8").strip().splitlines()
    except OSError as exc:
        return False, f"Cannot read pathgraph/history.jsonl: {exc}"

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry_ts = _parse_iso(entry.get("ts"))
        if entry_ts is None:
            continue
        if start_ts is None or entry_ts >= start_ts:
            return True, (
                f"PathGraph trace found: ts={entry.get('ts')}, "
                f"op_type={entry.get('op_type', 'unknown')}"
            )

    return False, (
        f"No pathgraph/history.jsonl entry with ts >= AP start_ts={start_ts_str}"
    )


# ---------------------------------------------------------------------------
# Bug lug writer
# ---------------------------------------------------------------------------

_CHECKPOINT_LINK_MAP: Dict[str, str] = {
    "V1": "L1",
    "V2": "L2",
    "V3": "L3",
    "V4": "L5",
    "V5": "L1+L5 full loop",
}


def _write_bug_lug(
    spoke_path: Path,
    checkpoint_id: str,
    detail: str,
    ap_run_start_ts: Optional[str],
) -> None:
    """Write a bug lug for a failing core checkpoint — only if one doesn't already exist today."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    lug_id = f"bug-rotation-check-{checkpoint_id}-{today}"
    bug_dir = _spoke_base(spoke_path) / "lugs" / "bytype" / "bug" / "open"
    bug_file = bug_dir / f"{lug_id}.json"

    if bug_file.exists():
        return  # idempotent — one bug per checkpoint per day

    bug_dir.mkdir(parents=True, exist_ok=True)
    broken_link = _CHECKPOINT_LINK_MAP.get(checkpoint_id, checkpoint_id)

    lug: Dict[str, Any] = {
        "id": lug_id,
        "type": "bug",
        "status": "open",
        "title": f"Wheel rotation checkpoint {checkpoint_id} failed: {detail}",
        "broken_link": broken_link,
        "detected_at": _iso_now(),
        "ap_run_start_ts": ap_run_start_ts,
        "parent_initiative": "initiative-wheel-rotation-wiring-v1",
    }

    try:
        bug_file.write_text(json.dumps(lug, indent=2) + "\n")
    except OSError:
        pass  # best-effort


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _run_checks(
    spoke_path: Path,
    hub_path: Optional[Path],
    ap_log_override: Optional[str],
    since_override: Optional[str],
) -> Dict[str, Any]:
    spoke_id = _get_spoke_id(spoke_path)

    # Locate AP log
    ap_log_path, ap_entry = _find_ap_log(spoke_path, ap_log_override)

    if ap_entry is None:
        ap_entry = {}

    # Determine AP run start_ts
    if since_override:
        ap_run_start_ts: Optional[str] = since_override
        # Inject into entry so checkpoints use it
        ap_entry = dict(ap_entry)
        ap_entry["run_at"] = since_override
    else:
        ap_run_start_ts = (
            ap_entry.get("run_at")
            or ap_entry.get("start_ts")
            or ap_entry.get("completed_at")
        )

    checkpoints: Dict[str, bool] = {}
    details: Dict[str, str] = {}
    advisory_failures: List[str] = []

    # V1
    try:
        v1_pass, v1_detail = check_V1(ap_entry, spoke_path)
    except Exception as exc:
        v1_pass, v1_detail = False, f"exception: {exc}"
    checkpoints["V1"] = v1_pass
    details["V1"] = v1_detail

    # V2
    try:
        v2_pass, v2_detail = check_V2(ap_entry)
    except Exception as exc:
        v2_pass, v2_detail = False, f"exception: {exc}"
    checkpoints["V2"] = v2_pass
    details["V2"] = v2_detail

    # V3
    try:
        v3_pass, v3_detail = check_V3(ap_entry, hub_path, spoke_id)
    except Exception as exc:
        v3_pass, v3_detail = False, f"exception: {exc}"
    checkpoints["V3"] = v3_pass
    details["V3"] = v3_detail

    # V4 — also extracts refresh_ts for V5
    try:
        v4_pass, v4_detail = check_V4_detail(ap_entry, hub_path)
        _, v4_refresh_ts = check_V4(ap_entry, hub_path)
    except Exception as exc:
        v4_pass, v4_detail = False, f"exception: {exc}"
        v4_refresh_ts = None
    checkpoints["V4"] = v4_pass
    details["V4"] = v4_detail

    # V5
    try:
        v5_pass, v5_detail = check_V5(spoke_path, v4_refresh_ts)
    except Exception as exc:
        v5_pass, v5_detail = False, f"exception: {exc}"
    checkpoints["V5"] = v5_pass
    details["V5"] = v5_detail

    # V6 (advisory)
    try:
        v6_pass, v6_detail = check_V6(ap_entry, spoke_path)
    except Exception as exc:
        v6_pass, v6_detail = False, f"exception: {exc}"
    checkpoints["V6"] = v6_pass
    details["V6"] = v6_detail
    if not v6_pass:
        advisory_failures.append("V6")

    # Determine loop_closed (V1-V5 only; V6 advisory)
    loop_closed = all(checkpoints[k] for k in ["V1", "V2", "V3", "V4", "V5"])

    # Broken links for failing core checkpoints
    broken_links: List[str] = []
    for ck in ["V1", "V2", "V3", "V4", "V5"]:
        if not checkpoints[ck]:
            broken_links.append(_CHECKPOINT_LINK_MAP.get(ck, ck))

    result: Dict[str, Any] = {
        "run_ts": _iso_now(),
        "ap_run_start_ts": ap_run_start_ts,
        "spoke_id": spoke_id,
        "checkpoints": checkpoints,
        "checkpoint_details": details,
        "loop_closed": loop_closed,
        "broken_links": broken_links,
        "error": None,
        "advisory_only_failures": advisory_failures,
    }

    return result


def _write_result(spoke_path: Path, result: Dict[str, Any]) -> Path:
    """Write rotation-check-latest.json and return its path."""
    health_dir = _advisors_base(spoke_path) / "health"
    health_dir.mkdir(parents=True, exist_ok=True)
    out_path = health_dir / "rotation-check-latest.json"
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    return out_path


def _print_table(result: Dict[str, Any]) -> None:
    """Print a human-readable summary table."""
    checkpoints = result["checkpoints"]
    details = result["checkpoint_details"]
    advisory = set(result.get("advisory_only_failures", []))

    header = f"{'Checkpoint':<12} {'Status':<8} Detail"
    print()
    print("=" * 80)
    print("  WHEEL ROTATION HEALTH CHECK")
    print(f"  Spoke:    {result['spoke_id']}")
    print(f"  AP start: {result['ap_run_start_ts'] or 'unknown'}")
    print(f"  Run at:   {result['run_ts']}")
    print("=" * 80)
    print(header)
    print("-" * 80)

    for ck in ["V1", "V2", "V3", "V4", "V5", "V6"]:
        passed = checkpoints.get(ck, False)
        status = "PASS" if passed else ("ADVISORY" if ck in advisory else "FAIL")
        detail = details.get(ck, "")
        # Wrap detail at 55 chars
        max_detail = 55
        if len(detail) > max_detail:
            detail = detail[:max_detail - 3] + "..."
        print(f"  {ck:<10} {status:<8} {detail}")

    print("-" * 80)
    loop_str = "CLOSED" if result["loop_closed"] else "OPEN"
    broken = result.get("broken_links", [])
    print(f"  Loop:     {loop_str}")
    if broken:
        print(f"  Broken:   {', '.join(broken)}")
    print("=" * 80)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wheel Rotation Health Check — verify the Navigator->AP->Hub intelligence loop."
    )
    parser.add_argument(
        "--spoke-path", default=".",
        help="Root of spoke (default: current directory)"
    )
    parser.add_argument(
        "--hub-path", default=None,
        help="Hub project root override (auto-detects from WAI-State.json if omitted)"
    )
    parser.add_argument(
        "--ap-log", default=None, dest="ap_log",
        help="Override path for AP log file"
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_only",
        help="Output JSON only, suppress human text"
    )
    parser.add_argument(
        "--since", default=None,
        help="ISO timestamp override for AP run start_ts (for debugging)"
    )
    args = parser.parse_args()

    spoke_path = Path(args.spoke_path).resolve()
    hub_path = _resolve_hub_path(spoke_path, args.hub_path)

    result: Dict[str, Any] = {
        "run_ts": _iso_now(),
        "ap_run_start_ts": None,
        "spoke_id": "unknown",
        "checkpoints": {},
        "checkpoint_details": {},
        "loop_closed": False,
        "broken_links": [],
        "error": None,
        "advisory_only_failures": [],
    }

    try:
        result = _run_checks(
            spoke_path=spoke_path,
            hub_path=hub_path,
            ap_log_override=args.ap_log,
            since_override=args.since,
        )
    except Exception as exc:
        result["error"] = str(exc)
        result["loop_closed"] = False

    # Write rotation-check-latest.json
    try:
        out_path = _write_result(spoke_path, result)
        if not args.json_only:
            print(f"[health-check] Written: {out_path}", file=sys.stderr)
    except Exception as exc:
        if not args.json_only:
            print(f"[health-check] WARNING: Could not write output file: {exc}", file=sys.stderr)

    # Write bug lugs for failing core checkpoints
    ap_run_start_ts = result.get("ap_run_start_ts")
    for ck in ["V1", "V2", "V3", "V4", "V5"]:
        if not result["checkpoints"].get(ck, True):
            try:
                _write_bug_lug(
                    spoke_path=spoke_path,
                    checkpoint_id=ck,
                    detail=result["checkpoint_details"].get(ck, "unknown failure"),
                    ap_run_start_ts=ap_run_start_ts,
                )
            except Exception:
                pass

    # Output
    if args.json_only:
        print(json.dumps(result, indent=2))
    else:
        _print_table(result)
        print(json.dumps(result, indent=2))

    # Exit code
    sys.exit(0 if result.get("loop_closed") else 1)


if __name__ == "__main__":
    main()
