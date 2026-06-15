#!/usr/bin/env python3
"""
initiative_measurer.py — Hypothesis verification runner for initiative work contracts.

Responsibilities:
  1. Detect active → measuring transition: when all epics in a focus-locked active
     initiative are in completed/ state, flip lifecycle_state to measuring and stamp
     measuring_started_at.
  2. Score measuring initiatives: after runs_required nightly cycles have elapsed
     (measured by checking activity_events or by counting nightly log entries),
     assess each success_criterion against collected data using a Claude haiku call.
  3. Write hypothesis_result (confirmed | refuted | partial) and modification_notes
     back to the per-file initiative source object.
  4. Move initiative file to the matching lifecycle_state subfolder on transition.
  5. On culmination (all epics complete + gate satisfied): set lifecycle_state=complete,
     write celebration_note, and move file to complete/ subfolder.
  6. Trigger index regeneration via tools/regen_indexes.sh after saves.
  7. Surface user checkpoint: print a clear banner when measuring is complete so
     it appears in the nightly log.

Usage:
  python3 tools/initiative_measurer.py                  # run full cycle
  python3 tools/initiative_measurer.py --dry-run        # detect only, no writes
  python3 tools/initiative_measurer.py --force-measure <initiative_id>  # skip run count gate
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

HEADLESS_LOG = _REPO_ROOT / "WAI-Spoke" / "advisors" / "headless" / "logs" / "nightly.log"
SUPABASE_REST = os.environ.get("SUPABASE_REST", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

ACTIVE_MEASURE_STATES = {"approved", "active", "measuring"}


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Per-file initiative I/O
# ---------------------------------------------------------------------------

def _load_initiatives(spoke_root: str) -> list:
    """Load all initiative per-file objects from bytype/initiative/**/*.json."""
    base = Path(spoke_root) / "WAI-Spoke" / "initiatives" / "bytype" / "initiative"
    initiatives = []
    if not base.exists():
        return initiatives
    for lifecycle_dir in sorted(base.iterdir()):
        if not lifecycle_dir.is_dir():
            continue
        for f in sorted(lifecycle_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text())
                d["_file_path"] = str(f)
                d["_lifecycle_dir"] = lifecycle_dir.name
                initiatives.append(d)
            except Exception:
                pass
    return initiatives


def _save_initiative(initiative: dict) -> None:
    """Write updated initiative back to its per-file source."""
    file_path = initiative.get("_file_path")
    if not file_path or not Path(file_path).exists():
        return
    # Strip internal tracking keys before writing
    clean = {k: v for k, v in initiative.items() if not k.startswith("_")}
    Path(file_path).write_text(json.dumps(clean, indent=2) + "\n")


def _regen_indexes(spoke_root: str) -> None:
    """Regenerate WAI-InitiativeIndex.jsonl and index.json read-model."""
    regen = Path(spoke_root) / "tools" / "regen_indexes.sh"
    if regen.exists():
        try:
            subprocess.run(["bash", str(regen), spoke_root], timeout=30, check=False)
        except Exception:
            pass


def _move_initiative_file(initiative: dict, new_lifecycle: str) -> None:
    """Move initiative file to the {new_lifecycle}/ subfolder."""
    old_path = Path(initiative["_file_path"])
    new_dir = old_path.parent.parent / new_lifecycle
    new_dir.mkdir(parents=True, exist_ok=True)
    new_path = new_dir / old_path.name
    if old_path != new_path:
        old_path.rename(new_path)
        initiative["_file_path"] = str(new_path)
        initiative["_lifecycle_dir"] = new_lifecycle
    initiative["lifecycle_state"] = new_lifecycle


# ---------------------------------------------------------------------------
# Health data (themes / impact ranking)
# ---------------------------------------------------------------------------

def _load_themes(spoke_root: str) -> dict:
    """Load themes from WAI-Spoke/health/themes.json."""
    themes_path = Path(spoke_root) / "WAI-Spoke" / "health" / "themes.json"
    if not themes_path.exists():
        return {}
    try:
        return json.loads(themes_path.read_text())
    except Exception:
        return {}


def _load_impact_ranking(spoke_root: str) -> list:
    """Load impact ranking from WAI-Spoke/health/impact-ranking.json."""
    ranking_path = Path(spoke_root) / "WAI-Spoke" / "health" / "impact-ranking.json"
    if not ranking_path.exists():
        return []
    try:
        return json.loads(ranking_path.read_text())
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Epic completion check
# ---------------------------------------------------------------------------

def all_epics_complete(initiative: dict, repo_root: Path) -> bool:
    """Return True if every epic in the initiative is in bytype/epic/completed/."""
    epics = initiative.get("epics", [])
    if not epics:
        return False
    completed_dir = repo_root / "WAI-Spoke" / "lugs" / "bytype" / "epic" / "completed"
    for epic_id in epics:
        if not (completed_dir / f"{epic_id}.json").exists():
            return False
    return True


# ---------------------------------------------------------------------------
# Nightly run counting
# ---------------------------------------------------------------------------

def count_nightly_runs_since(since_iso: str) -> int:
    """Count nightly log entries after since_iso by scanning the nightly log."""
    if not HEADLESS_LOG.exists():
        return 0
    since_dt = datetime.datetime.fromisoformat(since_iso.rstrip("Z")).replace(
        tzinfo=datetime.timezone.utc
    )
    count = 0
    try:
        for line in HEADLESS_LOG.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            # Lines may be JSON or plain text with a timestamp prefix
            try:
                entry = json.loads(line)
                ts_str = entry.get("ts", "")
            except json.JSONDecodeError:
                # Plain text: look for ISO timestamp at start
                ts_str = line[:25] if len(line) > 20 else ""
            if not ts_str:
                continue
            try:
                ts = datetime.datetime.fromisoformat(ts_str.rstrip("Z")).replace(
                    tzinfo=datetime.timezone.utc
                )
                if ts > since_dt:
                    count += 1
            except ValueError:
                pass
    except OSError:
        pass
    return count


# ---------------------------------------------------------------------------
# Activity events
# ---------------------------------------------------------------------------

def query_activity_events(window_days: int) -> list[dict]:
    """Pull recent activity_events rows from Supabase. Returns [] if unavailable."""
    if not SUPABASE_REST or not SUPABASE_KEY:
        return []
    since = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=window_days)
    ).isoformat()
    url = (
        f"{SUPABASE_REST.rstrip('/')}/activity_events"
        f"?ts=gte.{since}&order=ts.desc&limit=500"
    )
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        print(f"[measurer] activity_events query failed: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Claude scoring
# ---------------------------------------------------------------------------

def score_criteria_with_claude(
    initiative: dict, events: list[dict]
) -> dict:
    """
    Use claude haiku to score each success_criterion against the collected data.
    Returns {"result": "confirmed|refuted|partial", "notes": str, "scores": [{criterion, verdict, reason}]}
    """
    criteria = initiative.get("success_criteria", [])
    hypothesis = initiative.get("hypothesis", "")
    label = initiative.get("label", initiative.get("id", "?"))

    # Summarise events (keep under 2k tokens)
    event_summary = {
        "total_events": len(events),
        "event_types": {},
        "session_kinds": {},
        "outcomes": {},
    }
    for ev in events:
        for field, key in [("event_type", "event_types"), ("session_kind", "session_kinds"), ("outcome", "outcomes")]:
            val = ev.get(field, "unknown") or "unknown"
            event_summary[field.rstrip("s") if field != "event_types" else "event_types"][val] = \
                event_summary[key].get(val, 0) + 1

    prompt = f"""You are assessing whether an initiative hypothesis is confirmed by collected data.

Initiative: {label}
Hypothesis: {hypothesis}

Activity data summary (last {initiative.get("completion_gate", {}).get("measurement_window_days", 7)} days):
{json.dumps(event_summary, indent=2)}

Success criteria to score (each: passed | failed | partial | insufficient_data):
{chr(10).join(f"{i+1}. {c}" for i, c in enumerate(criteria))}

Respond with valid JSON only:
{{
  "scores": [
    {{"criterion": "...", "verdict": "passed|failed|partial|insufficient_data", "reason": "one sentence"}}
  ],
  "overall": "confirmed|refuted|partial",
  "modification_notes": "one paragraph recommendation for next steps or criteria adjustments"
}}"""

    try:
        result = subprocess.run(
            ["claude", "--print", "--model", "claude-haiku-4-5-20251001",
             "--no-session-persistence", "-p", prompt],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:200])
        # Extract JSON from output (claude may add prose)
        output = result.stdout.strip()
        start = output.find("{")
        end = output.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(output[start:end])
    except Exception as exc:
        print(f"[measurer] claude scoring failed: {exc}", file=sys.stderr)

    # Fallback: mark as insufficient_data
    return {
        "scores": [{"criterion": c, "verdict": "insufficient_data", "reason": "scoring unavailable"} for c in criteria],
        "overall": "partial",
        "modification_notes": "Automated scoring unavailable — manual review required.",
    }


# ---------------------------------------------------------------------------
# Main run loop
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, force_measure: str = "", spoke_root: str = "") -> dict:
    if not spoke_root:
        spoke_root = str(_REPO_ROOT)

    initiatives = _load_initiatives(spoke_root)
    report = {"transitions": [], "scored": [], "errors": []}
    any_saved = False

    for init in initiatives:
        iid = init.get("id", "")
        state = init.get("lifecycle_state", "proposed")

        # Force-measure override
        if force_measure and iid != force_measure:
            continue

        # --- Transition: active → measuring ---
        if state == "active" and all_epics_complete(init, Path(spoke_root)):
            print(f"[measurer] {iid}: all epics complete → measuring")
            if not dry_run:
                old_state = state
                init["measuring_started_at"] = now_iso()
                _move_initiative_file(init, "measuring")
                init["lifecycle_state"] = "measuring"
                _save_initiative(init)
                any_saved = True
            report["transitions"].append({"id": iid, "from": "active", "to": "measuring"})

        # --- Score: measuring → complete ---
        current_state = init.get("lifecycle_state", state)
        if current_state != "measuring" and not force_measure:
            continue

        gate = init.get("completion_gate", {})
        runs_required = gate.get("runs_required", 5)
        window_days = gate.get("measurement_window_days", 7)
        measuring_since = init.get("measuring_started_at", now_iso())

        runs_collected = count_nightly_runs_since(measuring_since)
        print(f"[measurer] {iid}: {runs_collected}/{runs_required} runs collected")

        if runs_collected < runs_required and not force_measure:
            print(f"[measurer] {iid}: waiting for more runs (need {runs_required - runs_collected} more)")
            continue

        print(f"[measurer] {iid}: scoring hypothesis against {window_days}d of data")
        events = query_activity_events(window_days)
        scoring = score_criteria_with_claude(init, events)

        print(f"[measurer] {iid}: hypothesis_result = {scoring.get('overall', '?')}")
        print(f"[measurer] {iid}: notes = {scoring.get('modification_notes', '')[:120]}")

        # User checkpoint banner
        print()
        print("=" * 70)
        print(f"INITIATIVE CHECKPOINT — {init.get('label', iid)}")
        print(f"Hypothesis result: {scoring.get('overall', 'unknown').upper()}")
        for s in scoring.get("scores", []):
            verdict = s.get("verdict", "?")
            icon = "✓" if verdict == "passed" else "✗" if verdict == "failed" else "~"
            print(f"  {icon} {s.get('criterion', '')[:70]} — {verdict}")
        print(f"Recommendation: {scoring.get('modification_notes', '')[:200]}")

        # Check culmination: all criteria passed and gate satisfied
        all_passed = all(
            s.get("verdict") == "passed" for s in scoring.get("scores", [])
        )
        if not dry_run:
            init["hypothesis_result"] = scoring.get("overall")
            init["modification_notes"] = scoring.get("modification_notes")

            if all_passed and scoring.get("overall") == "confirmed":
                # Culmination — flip to complete
                label = init.get("label", iid)
                init["celebration_note"] = (
                    f"Initiative '{label}' has culminated! "
                    f"All epics complete and completion gate satisfied."
                )
                _move_initiative_file(init, "complete")
                init["lifecycle_state"] = "complete"
                _save_initiative(init)
                any_saved = True
                print(f"[measurer] {iid}: CULMINATED — lifecycle_state=complete, celebration_note written")
                print(f"  celebration: {init['celebration_note']}")
            else:
                # Leave lifecycle_state as measuring — user must approve → complete
                # (set via manual session or future user-checkpoint gate)
                _save_initiative(init)
                any_saved = True

        if all_passed and scoring.get("overall") == "confirmed":
            print("STATUS: CULMINATED — initiative is complete!")
        else:
            print("ACTION REQUIRED: Review and approve in wakeup session before marking complete.")
        print("=" * 70)
        print()

        report["scored"].append({
            "id": iid,
            "result": scoring.get("overall"),
            "runs": runs_collected,
            "culminated": all_passed and scoring.get("overall") == "confirmed",
        })

    if not dry_run and any_saved:
        _regen_indexes(spoke_root)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-measure", default="", help="Force measure a specific initiative ID")
    parser.add_argument("--spoke-root", default="", help="Override repo root (default: auto-detect from script location)")
    args = parser.parse_args()
    result = run(dry_run=args.dry_run, force_measure=args.force_measure, spoke_root=args.spoke_root)
    print(json.dumps(result, indent=2))
