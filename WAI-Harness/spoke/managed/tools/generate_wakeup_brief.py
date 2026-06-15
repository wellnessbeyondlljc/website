#!/usr/bin/env python3
"""Generate WAI-Spoke/wakeup-brief.json.

Run before launching an AI tool to guarantee the wakeup fast path.
The wakeup protocol (wai.md Step 7) checks git_sha_at_generation against
HEAD — if they match, it skips all tool calls and displays the brief in seconds.

Usage:
    python3 tools/generate_wakeup_brief.py [--spoke-path /absolute/path/to/spoke_root]
"""

import datetime
import json
import os
import subprocess
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spoke_integrity_score import hook_freshness_check

# Lug leasing (optional — graceful fallback if module absent)
try:
    import lug_lease
    _LEASE_AVAILABLE = True
except ImportError:
    _LEASE_AVAILABLE = False

# Initiative leasing (optional — graceful fallback if module absent)
try:
    import initiative_lease
    _INITIATIVE_LEASE_AVAILABLE = True
except ImportError:
    _INITIATIVE_LEASE_AVAILABLE = False

# Pattern Health (AC8) — optional; graceful fallback if the miner is absent
try:
    from historian_gate_mine import pattern_health as _pattern_health
    _PATTERN_HEALTH_AVAILABLE = True
except ImportError:
    _PATTERN_HEALTH_AVAILABLE = False

# Quality Health (AC30) — optional; coverage/certification over v4 lugs
try:
    from compute_coverage import read_coverage as _read_coverage
    _QUALITY_HEALTH_AVAILABLE = True
except ImportError:
    _QUALITY_HEALTH_AVAILABLE = False

# AC Drift (impl-derive-epic-ac-status-v1) — optional; epic AC checkbox vs lug
# evidence drift per open epic. Surfaced so under/over/mis-partial reporting is
# visible at session open instead of discovered by hand mid-session.
try:
    from reconcile_epic_acs import read_ac_drift as _read_ac_drift
    _AC_DRIFT_AVAILABLE = True
except ImportError:
    _AC_DRIFT_AVAILABLE = False

# QA suite health (impl-qa-stale-test-detection-v1) — optional; stale-test detection
# + the test-null/stale/failing gap taxonomy over v4 lugs (the freshness half the
# coverage compute does not surface).
try:
    from qa_suite_health import read_qa_health as _read_qa_health
    _QA_HEALTH_AVAILABLE = True
except ImportError:
    _QA_HEALTH_AVAILABLE = False


def collect_active_leases(spoke: "Path") -> list:
    """Return live lug leases for the wakeup brief (sweeps expired first)."""
    if not _LEASE_AVAILABLE:
        return []
    store = spoke / "runtime" / "claims-local.json"
    try:
        leases = lug_lease.active_leases(store_path=str(store))
    except Exception:
        return []
    return [
        {
            "lug_id": l["lug_id"],
            "held_by": l["held_by"],
            "expires_at": l["expires_at"],
        }
        for l in leases
    ]

def scan_session_goals(spoke: "Path") -> dict:
    """Scan session tracks for unresolved goal_set events.

    Returns {'user_required': [...], 'ozi_eligible': [...]} where each entry is:
    {session_id, initiative_id, goals: [{goal_id, description, requires_user_input}],
     last_active, ozi_eligible}
    """
    import time as _time
    from datetime import datetime as _dt, timezone as _tz
    sessions_dir = spoke / "sessions"
    result: dict = {"user_required": [], "ozi_eligible": []}
    if not sessions_dir.exists():
        return result
    cutoff_days = 30
    for track_file in sorted(sessions_dir.glob("session-*/track.jsonl"), reverse=True):
        try:
            lines = track_file.read_text().splitlines()
        except OSError:
            continue
        goals_set: dict = {}
        goals_done: set = set()
        last_ts: str = ""
        initiative_id: str = ""
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ts = entry.get("ts", "")
            if ts:
                last_ts = ts
            ev = entry.get("event", "")
            if ev == "goal_set":
                gid = entry.get("goal_id", "")
                if gid:
                    goals_set[gid] = entry
            elif ev == "goal_completed":
                gid = entry.get("goal_id", "")
                if gid:
                    goals_done.add(gid)
            elif ev in ("savepoint", "session_start") and entry.get("initiative_id"):
                initiative_id = entry["initiative_id"]
        outstanding = [goals_set[g] for g in goals_set if g not in goals_done]
        if not outstanding:
            continue
        if last_ts:
            try:
                ts_dt = _dt.fromisoformat(last_ts.replace("Z", "+00:00"))
                age_days = (_dt.now(_tz.utc) - ts_dt).days
                if age_days > cutoff_days:
                    continue
            except Exception:
                pass
        session_id = track_file.parent.name
        needs_user = any(g.get("requires_user_input", False) for g in outstanding)
        entry_out = {
            "session_id": session_id,
            "initiative_id": initiative_id or None,
            "goals": [
                {
                    "goal_id": g["goal_id"],
                    "description": g.get("description", ""),
                    "requires_user_input": g.get("requires_user_input", False),
                }
                for g in outstanding
            ],
            "last_active": last_ts,
            "ozi_eligible": not needs_user,
        }
        if needs_user:
            result["user_required"].append(entry_out)
        else:
            result["ozi_eligible"].append(entry_out)
    return result


def generate_session_resume_brief(session_dir: "Path") -> str:
    """5-8 line rewarm brief for a session. Returns plain text."""
    session_dir = Path(session_dir)
    track_path = session_dir / "track.jsonl"
    if not track_path.exists():
        return f"Session {session_dir.name}: no track found."
    goals_set: dict = {}
    goals_done: set = set()
    turns: list = []
    initiative_id: str = ""
    open_items: list = []
    for raw in track_path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ev = entry.get("event", "")
        if ev == "goal_set":
            gid = entry.get("goal_id", "")
            if gid:
                goals_set[gid] = entry
        elif ev == "goal_completed":
            gid = entry.get("goal_id", "")
            if gid:
                goals_done.add(gid)
        elif entry.get("turn"):
            turns.append(entry)
            open_items = entry.get("open", []) or []
        elif ev in ("savepoint", "session_start") and entry.get("initiative_id"):
            initiative_id = entry["initiative_id"]
    session_name = session_dir.name
    last_turns = turns[-3:] if turns else []
    outstanding = [(g, goals_set[g]) for g in goals_set if g not in goals_done]
    lines_out = [
        f"Session {session_name}"
        + (f" (initiative: {initiative_id})" if initiative_id else "")
    ]
    if outstanding:
        lines_out.append("Outstanding goals:")
        for _gid, grec in outstanding:
            ri = "  [needs you]" if grec.get("requires_user_input") else ""
            lines_out.append(f"  [ ] {grec.get('description', _gid)}{ri}")
    else:
        lines_out.append("Goals: all complete (or none set)")
    if last_turns:
        last = last_turns[-1]
        action_str = str(last.get("action", ""))[:120]
        lines_out.append(f"Last action (turn {last.get('turn', '?')}): {action_str}")
    if open_items:
        lines_out.append("Open items from last turn:")
        for item in open_items[:3]:
            lines_out.append(f"  - {item}")
    return "\n".join(lines_out)


def build_continuation_menu(spoke: "Path") -> dict:
    """Populate continuation_menu for the wakeup brief.

    Returns {initiatives: [...], pending_savepoints: [...]} for finish-before-start prioritization.
    """
    try:
        initiatives_full: list = []
        initiatives_index = spoke / "initiatives" / "WAI-InitiativeIndex.jsonl"
        if initiatives_index.exists():
            try:
                for line in initiatives_index.read_text().strip().split('\n'):
                    if not line:
                        continue
                    ini = json.loads(line)
                    if ini.get("lifecycle_state") not in ("approved", "measuring"):
                        continue
                    initiatives_full.append(ini)
            except Exception:
                pass

        initiatives_full.sort(key=lambda x: (-int(x.get("focus_lock", False)), x.get("impact_rank", 99)))
        initiatives = [
            {
                "id": ini.get("id", ""),
                "label": ini.get("label", ini.get("id", "")),
                "lifecycle_state": ini.get("lifecycle_state", ""),
                "focus_lock": ini.get("focus_lock", False),
            }
            for ini in initiatives_full[:3]
        ]

        pending_savepoints: list = []
        savepoint_file = spoke / "runtime" / "savepoint.json"
        if savepoint_file.exists():
            try:
                savepoint_data = json.loads(savepoint_file.read_text())
                if savepoint_data.get("status") == "pending":
                    pending_savepoints.append(savepoint_data)
            except Exception:
                pass

        return {"initiatives": initiatives, "pending_savepoints": pending_savepoints}
    except Exception:
        return {"initiatives": [], "pending_savepoints": []}


PROJECT_DIR = Path(__file__).parent.parent
# Default to CWD if it's a WAI spoke

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wai_paths  # noqa: E402  harness-mode root resolver (single source of truth)

# These are now determined after parsing args.
# SPOKE is the working BASE (v3: <root>/WAI-Spoke ; v4-only: <root>/WAI-Harness/spoke/local).
# PROJECT_ROOT is the spoke project dir that CONTAINS that base — it is NOT SPOKE.parent
# in v4 (where SPOKE.parent is .../WAI-Harness/spoke), so it is tracked explicitly.
SPOKE = None
PROJECT_ROOT = None
BYTYPE = None
STATE_FILE = None
BRIEF_FILE = None


def _project_root_for(spoke) -> Path:
    """Map a working BASE back to its spoke project root, layout-aware, so the
    coverage/drift/qa helpers stay self-contained (callable without main()):
      v3 base  <root>/WAI-Spoke               -> <root>
      v4 base  <root>/WAI-Harness/spoke/local -> <root>
    Falls back to the base itself if the layout is unrecognised."""
    sp = Path(spoke)
    if sp.name == "WAI-Spoke":
        return sp.parent
    if sp.parts[-3:] == ("WAI-Harness", "spoke", "local"):
        return sp.parents[2]
    return sp


_NON_WORK_TYPES = {"signal", "spec", "phone-home"}  # non-executable, excluded from "work" bucket

def count_open_lugs() -> dict:
    """Return lug counts broken down by bucket: total, epics, work_open, work_ip."""
    counts = {"total": 0, "epics": 0, "work_open": 0, "work_ip": 0}
    if not BYTYPE.exists():
        return counts
    for type_dir in BYTYPE.iterdir():
        if not type_dir.is_dir():
            continue
        t = type_dir.name.lower()
        for status in ("open", "in_progress"):
            status_dir = type_dir / status
            try:
                n = len(list(status_dir.glob("*.json")))
                if n == 0:
                    continue
                counts["total"] += n
                if t == "epic":
                    counts["epics"] += n
                elif t not in _NON_WORK_TYPES:
                    counts["work_open" if status == "open" else "work_ip"] += n
            except (FileNotFoundError, PermissionError):
                pass
    return counts


def run_score_backlog() -> tuple[dict, list, list]:
    """Run score_backlog.py --update-state, then read updated _work_queue from state.

    Returns (queue_snapshot, top_ready_lugs, stalled_lugs).
    """
    score_script = PROJECT_DIR / "tools" / "score_backlog.py"
    if not score_script.exists():
        return {"ready_count": 0, "needs_refinement_count": 0, "blocked_count": 0, "stalled_count": 0}, [], []

    # Ensure score_backlog uses the correct spoke_path if provided
    score_cmd = [sys.executable, str(score_script), "--update-state"]
    if PROJECT_ROOT:  # the project dir containing the active harness base
        score_cmd.extend(["--spoke-path", str(PROJECT_ROOT)])

    subprocess.run(
        score_cmd,
        cwd=str(PROJECT_DIR),
        capture_output=True,
        timeout=30,
    )

    # Reload state to get updated _work_queue
    try:
        state = json.loads(STATE_FILE.read_text())
        wq = state.get("_work_queue", {})
        queue_snapshot = wq.get(
            "queue_state",
            {"ready_count": 0, "needs_refinement_count": 0, "blocked_count": 0, "stalled_count": 0},
        )
        top_lugs = [
            {k: item[k] for k in ("id", "title", "roi") if k in item}
            for item in wq.get("items", [])[:5]
            if item.get("readiness") == "ready"
        ]
        stalled_lugs = [
            {
                "id": item["id"],
                "title": item.get("title", ""),
                "roi": item.get("roi"),
                "annotation": (
                    "no estimated_seconds — consider setting based on effort+model"
                    if not item.get("has_estimated_seconds")
                    else None
                ),
            }
            for item in wq.get("items", [])
            if item.get("readiness") == "stalled"
        ]
        return queue_snapshot, top_lugs, stalled_lugs
    except Exception:
        return {"ready_count": 0, "needs_refinement_count": 0, "blocked_count": 0, "stalled_count": 0}, [], []


def load_tastegraph_prefs(spoke: "Path") -> dict:
    """Load TasteGraph preferences and format a compact injection block.

    Returns dict with keys: total_prefs, injected, categories_present, block.
    On failure returns graceful degradation dict.
    """
    tastegraph_path = spoke / "tastegraph.json"
    if not tastegraph_path.exists():
        return {"total_prefs": 0, "injected": 0, "error": "tastegraph not found", "block": ""}

    try:
        data = json.loads(tastegraph_path.read_text())
    except Exception as e:
        return {"total_prefs": 0, "injected": 0, "error": f"parse error: {e}", "block": ""}

    prefs = data.get("preferences", [])
    total_prefs = len(prefs)

    # Filter to stated and verified confidence only, with an explicit exception
    # for the compiled render contract used to shape agent responses.
    allowed_confidence = {"stated", "verified"}
    always_include_keys = {"render_contract"}
    filtered = [
        p
        for p in prefs
        if p.get("confidence") in allowed_confidence or p.get("key") in always_include_keys
    ]

    # Category priority order
    category_priority = ["accessibility", "communication", "cost_sensitivity", "temporal", "trust"]

    def category_sort_key(cat: str) -> int:
        try:
            return category_priority.index(cat)
        except ValueError:
            return len(category_priority)

    # Group by category
    grouped: dict = {}
    for pref in filtered:
        cat = pref.get("category", "other")
        grouped.setdefault(cat, []).append(pref)

    # Sort categories by priority
    sorted_cats = sorted(grouped.keys(), key=category_sort_key)

    # Format value: if dict, flatten to key=value pairs; otherwise stringify
    def format_value(val) -> str:
        if isinstance(val, dict):
            parts = []
            for k, v in val.items():
                if isinstance(v, (list, dict)):
                    parts.append(f"{k}: {json.dumps(v)}")
                else:
                    parts.append(f"{k}: {v}")
            return "; ".join(parts)
        elif isinstance(val, list):
            return ", ".join(str(x) for x in val)
        else:
            return str(val)

    # Build lines, respecting ~150 word (~200 token) hard cap
    # Priority categories (accessibility + communication) always kept complete
    priority_cats = {"accessibility", "communication"}
    word_budget = 150
    words_used = 0
    lines: list[str] = []
    categories_present: list[str] = []
    total_injected = 0
    truncated_at_cat = None
    truncated_remaining = 0

    for cat in sorted_cats:
        cat_prefs = grouped[cat]
        cat_header = cat.upper().replace("_", " ")
        cat_lines = [cat_header]
        for pref in cat_prefs:
            key = pref.get("key", pref.get("id", "?"))
            val = format_value(pref.get("value", ""))
            # Truncate very long values
            if len(val) > 120:
                val = val[:117] + "..."
            cat_lines.append(f"  {key}: {val}")

        # Count words for these lines
        block_words = sum(len(line.split()) for line in cat_lines)

        if cat in priority_cats or words_used + block_words <= word_budget:
            lines.extend(cat_lines)
            words_used += block_words
            categories_present.append(cat)
            total_injected += len(cat_prefs)
        else:
            # Truncate: count remaining prefs not yet injected
            remaining = sum(len(grouped[c]) for c in sorted_cats if c not in categories_present)
            truncated_at_cat = cat
            truncated_remaining = remaining
            break

    if truncated_remaining > 0:
        lines.append(f"  (+{truncated_remaining} more)")

    block = "\n".join(lines)

    return {
        "total_prefs": total_prefs,
        "injected": total_injected,
        "categories_present": categories_present,
        "block": block,
    }


def count_teachings_pending(hub_path: str, spoke: "Optional[Path]" = None) -> int:
    """Count unprocessed teachings from hub.

    Scans the same paths as session-start.sh (node-type-aware) PLUS the legacy
    framework/current/ directory, deduplicating by filename so neither source is missed.
    """
    if not hub_path:
        return 0
    hub = Path(hub_path).expanduser()
    processed_dir = (spoke if spoke else SPOKE) / "seed" / "ingest" / "processed"
    # Node-type-aware paths (mirrors session-start.sh logic)
    try:
        _state_file = (spoke if spoke else SPOKE) / "WAI-State.json"
        _node_type = json.loads(_state_file.read_text()).get("wheel", {}).get("node_type", "spoke")
    except Exception:
        _node_type = "spoke"
    if _node_type == "hub":
        scan_dirs = [hub / "teachings_repo" / "hub-only" / "current",
                     hub / "teachings_repo" / "cross_spoke" / "current"]
    else:
        scan_dirs = [hub / "teachings_repo" / "spoke" / "current",
                     hub / "teachings_repo" / "cross_spoke" / "current"]
    # Legacy path — keep scanning until hub is fully migrated
    scan_dirs.append(hub / "teachings_repo" / "framework" / "current")
    seen: set = set()
    count = 0
    for teach_dir in scan_dirs:
        if not teach_dir.exists():
            continue
        for f in teach_dir.glob("*.teaching"):
            if f.name in seen:
                continue
            seen.add(f.name)
            if not (processed_dir / f.name).exists():
                count += 1
    return count


def count_incoming_lugs(spoke: "Optional[Path]" = None) -> int:
    """Count unprocessed lugs in the spoke's lugs/incoming/ (excludes processed/ and completed/).

    `spoke` is the already-resolved working base (v3: <root>/WAI-Spoke, v4: <root>/WAI-Harness/spoke/local),
    so lugs/incoming below it is harness-mode-correct."""
    incoming = (spoke if spoke else SPOKE) / "lugs" / "incoming"
    if not incoming.exists():
        return 0
    skip_dirs = {incoming / "processed", incoming / "completed"}
    return sum(
        1 for f in incoming.glob("*.json")
        if f.is_file() and f.parent not in skip_dirs
    )


def count_hub_signals(hub_path: str) -> int:
    if not hub_path:
        return 0
    base = Path(hub_path).expanduser() / "WAI-Hub" / "signals" / "incoming"
    total = 0
    for subfolder in ("framework", "spokes"):
        sig_dir = base / subfolder
        if sig_dir.exists():
            total += len([f for f in sig_dir.glob("*.json") if f.name != ".gitkeep"])
    return total


def read_work_queue_matrix_counts(spoke: "Optional[Path]") -> dict:
    """Read work-queue.json from Expediter and return autopilot-ready vs needs-you totals."""
    if not spoke:
        return {}
    wq_path = spoke / "advisors" / "expediter" / "work-queue.json"
    if not wq_path.exists():
        return {}
    try:
        wq = json.loads(wq_path.read_text())
        totals = wq.get("totals", {})
        return {
            "autopilot_ready": totals.get("autonomous", 0),
            "needs_you": totals.get("attended", 0),
            "schema_version": wq.get("schema_version", ""),
        }
    except (OSError, json.JSONDecodeError):
        return {}


def read_pattern_health(spoke: "Optional[Path]") -> "Optional[dict]":
    """AC8: the wakeup Pattern Health section — first-attempt approval rate per
    flow, halt frequency per step, open-candidate count. Reads the gate-log +
    historian candidates and computes via historian_gate_mine.pattern_health().

    Degrades gracefully (returns None) if the miner is unavailable or there is no
    gate-log yet — never blocks brief generation. Carries a freshness marker so a
    stale/empty section self-flags rather than appearing authoritative."""
    if not spoke or not _PATTERN_HEALTH_AVAILABLE:
        return None
    gate_log = spoke / "patterns" / "gate-log.jsonl"
    if not gate_log.exists():
        return {"status": "no-gate-log-yet", "first_attempt_approval_rate": {},
                "halt_frequency_per_step": {}, "open_candidates": 0,
                "source": str(gate_log.relative_to(spoke.parent)) if spoke else ""}
    try:
        events = []
        for line in gate_log.read_text().splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        cand_dir = spoke / "advisors" / "historian" / "patterns" / "candidates"
        candidates = sorted(cand_dir.glob("*.json")) if cand_dir.exists() else []
        health = _pattern_health(events, candidates, trigger_fired=False)
        health["status"] = "ok"
        health["event_count"] = len(events)
        return health
    except (OSError, json.JSONDecodeError, ValueError):
        return {"status": "unreadable", "first_attempt_approval_rate": {},
                "halt_frequency_per_step": {}, "open_candidates": 0}


def read_quality_health(spoke: "Optional[Path]") -> "Optional[dict]":
    """AC30: the wakeup Quality Health section — lug coverage %, null rate,
    certification_score, uncertified lugs — computed over v4 lugs. Degrades
    gracefully (None) if the computer is unavailable; never blocks brief generation."""
    if not spoke or not _QUALITY_HEALTH_AVAILABLE:
        return None
    try:
        return _read_coverage(str(_project_root_for(spoke)))
    except Exception:
        return {"status": "unreadable", "certification_score": None,
                "ac_coverage_pct": None, "null_rate": None, "uncertified_lugs": []}


def read_ac_drift(spoke: "Optional[Path]") -> "Optional[dict]":
    """impl-derive-epic-ac-status-v1: per-open-epic AC drift vs lug evidence
    {epic_id: {under_report, over_report, mis_partial, total_drift}}. Degrades
    gracefully (None) if the reconciler is unavailable; never blocks brief gen."""
    if not spoke or not _AC_DRIFT_AVAILABLE:
        return None
    try:
        return _read_ac_drift(str(_project_root_for(spoke)))
    except Exception:
        return {}


def read_qa_health(spoke: "Optional[Path]") -> "Optional[dict]":
    """impl-qa-stale-test-detection-v1: stale-test detection + gap taxonomy
    (test_null/stale/failing) over v4 lugs. Additive to quality_health (which
    carries coverage/cert). Degrades gracefully (None) if the module is absent."""
    if not spoke or not _QA_HEALTH_AVAILABLE:
        return None
    try:
        return _read_qa_health(str(_project_root_for(spoke)))
    except Exception:
        return {"gap_summary": {"test_null": 0, "stale": 0, "failing": 0},
                "stale_tests": [], "status": "unreadable"}


def get_git_sha(spoke_root_path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(spoke_root_path),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return ""


def main() -> None:
    global SPOKE, PROJECT_ROOT, BYTYPE, STATE_FILE, BRIEF_FILE

    parser = argparse.ArgumentParser(description="Generate the spoke wakeup-brief.json (harness-mode aware).")
    parser.add_argument(
        "--spoke-path",
        type=str,
        help="Absolute path to the spoke root directory (e.g., /home/user/projects/minder)",
        default=None,
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="v4-only | v3-only (else $WAI_HARNESS_MODE / auto: prefer v4).",
    )
    args = parser.parse_args()

    # Determine the PROJECT ROOT (dir containing WAI-Spoke and/or WAI-Harness), then
    # resolve the working BASE via the single-source resolver so a v4-only session
    # briefs from WAI-Harness/spoke/local with zero WAI-Spoke access.
    if args.spoke_path:
        PROJECT_ROOT = Path(args.spoke_path)
        if not ((PROJECT_ROOT / "WAI-Spoke").exists() or (PROJECT_ROOT / "WAI-Harness").exists()):
            print(f"ERROR: --spoke-path {args.spoke_path} contains neither WAI-Spoke nor WAI-Harness.", file=sys.stderr)
            sys.exit(1)
    elif (Path.cwd() / "WAI-Spoke").exists() or (Path.cwd() / "WAI-Harness").exists():
        PROJECT_ROOT = Path.cwd()
    else:
        PROJECT_ROOT = PROJECT_DIR

    base, mode = wai_paths.resolve_wai_root(str(PROJECT_ROOT), args.mode)
    if not base:
        print(f"ERROR: no WAI harness tree (WAI-Spoke or WAI-Harness) under {PROJECT_ROOT}", file=sys.stderr)
        sys.exit(1)
    SPOKE = Path(base)

    if not SPOKE.exists():
        print(f"ERROR: resolved working base does not exist at {SPOKE} (mode={mode})", file=sys.stderr)
        sys.exit(1)

    # Update global path variables based on the determined SPOKE path
    BYTYPE = SPOKE / "lugs" / "bytype"
    STATE_FILE = SPOKE / "WAI-State.json"
    BRIEF_FILE = SPOKE / "wakeup-brief.json"

    if not STATE_FILE.exists():
        print(f"ERROR: WAI-State.json not found at {STATE_FILE} — not a WAI project", file=sys.stderr)
        sys.exit(1)

    state = json.loads(STATE_FILE.read_text())
    hub_path = state.get("wheel", {}).get("hub_path", "")
    spoke_version = state.get("wheel", {}).get("version", "unknown")
    last_session_id = state.get("_session_state", {}).get("last_session_id", "unknown")
    next_rec = state.get("_session_state", {}).get(
        "next_session_recommendation", "None"
    )

    intent_file = SPOKE / "runtime" / "session-intent.json"
    session_intent = None
    if intent_file.exists():
        try:
            session_intent = json.loads(intent_file.read_text())
        except Exception:
            pass
    savepoint = state.get("_savepoint", {})
    savepoint_data = savepoint if savepoint.get("status") == "pending" else None

    lug_counts = count_open_lugs()
    open_lug_count = lug_counts["total"]
    queue_snapshot, top_ready_lugs, stalled_lugs = run_score_backlog()
    work_queue_matrix = read_work_queue_matrix_counts(SPOKE)
    teachings_pending = count_teachings_pending(hub_path, SPOKE)
    incoming_lugs_pending = count_incoming_lugs(SPOKE)
    hub_signals_pending = count_hub_signals(hub_path)
    git_sha = get_git_sha(PROJECT_ROOT)  # the spoke project root (NOT SPOKE.parent in v4)
    hook_freshness = hook_freshness_check(PROJECT_ROOT, PROJECT_DIR)
    tastegraph_prefs = load_tastegraph_prefs(SPOKE)
    active_leases = collect_active_leases(SPOKE)
    continuation_menu = build_continuation_menu(SPOKE)
    pattern_health_data = read_pattern_health(SPOKE)
    quality_health_data = read_quality_health(SPOKE)
    ac_drift_data = read_ac_drift(SPOKE)
    qa_health_data = read_qa_health(SPOKE)

    brief = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": last_session_id,
        "generation_mode": "standard",
        "chain_target_lug": None,
        "open_lug_count": open_lug_count,
        "queue_snapshot": queue_snapshot,
        "top_ready_lugs": top_ready_lugs,
        "stalled_lugs": stalled_lugs,
        "teachings_pending": teachings_pending,
        "incoming_lugs_pending": incoming_lugs_pending,
        "hub_signals_pending": hub_signals_pending,
        "intent": session_intent.get("intent") if session_intent else None,
        "intent_label": session_intent.get("intent_label") if session_intent else None,
        "savepoint": savepoint_data,
        "next_session_goal": next_rec,
        "next_actions": [next_rec],
        "spoke_version": spoke_version,
        "git_sha_at_generation": git_sha,
        "hook_freshness": hook_freshness,
        "tastegraph_prefs": tastegraph_prefs,
        "active_leases": active_leases,
        "continuation_menu": continuation_menu,
        "work_queue_matrix": work_queue_matrix,
        "pattern_health": pattern_health_data,
        "quality_health": quality_health_data,
        "ac_drift": ac_drift_data,
        "qa_health": qa_health_data,
    }

    # Atomic write
    tmp = BRIEF_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(brief, indent=2) + "\n")
    os.replace(tmp, BRIEF_FILE)

    sha8 = git_sha[:8] if git_sha else "unknown"
    _parts = []
    if lug_counts["epics"] > 0:
        _parts.append(f"{lug_counts['epics']} epics")
    _work = lug_counts["work_open"] + lug_counts["work_ip"]
    if _work > 0:
        _parts.append(f"{_work} work")
    _lug_summary = " | ".join(_parts) if _parts else "0 open"
    _stalled = queue_snapshot.get("stalled_count", 0)
    _stalled_suffix = f" | {_stalled} stalled" if _stalled > 0 else ""
    print(
        f"wakeup-brief.json updated | SHA {sha8} | "
        f"{_lug_summary} | queue {queue_snapshot.get('ready_count', 0)} ready{_stalled_suffix}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
