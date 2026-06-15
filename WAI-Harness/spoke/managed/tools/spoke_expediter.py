#!/usr/bin/env python3
"""
Spoke-Local Expediter — Lug Quality Scorer + Signal Triage + AP Routing

Scores all active lugs on PEV completeness (0-10), generates a priority-ordered
refinement queue, optionally triages undelivered signals, and auto-sets execution_mode
based on quality score, model_fit, and routing target.

Cost model:
    FAST sort runs every time (cheap, no LLM): score + categorize + route + emit the
    two-tray ready-queue.json. The heavier HYGIENE sweep (rglobs all lugs and emits
    coverage-gap work that costs tokens downstream) auto-escalates only when the
    autonomous backlog is low (<= HYGIENE_LOW_WATERMARK dispatchable), periodically
    (>= HYGIENE_STALE_DAYS since last sweep), or when forced with --hygiene/--all.

Usage:
    python3 tools/spoke_expediter.py                       # Fast sort (auto-escalates to hygiene when low/stale)
    python3 tools/spoke_expediter.py --all                 # Force full flow (score + hygiene + signals + emit)
    python3 tools/spoke_expediter.py --hygiene             # Force the hygiene sweep this run
    python3 tools/spoke_expediter.py --signals             # Also triage signals
    python3 tools/spoke_expediter.py --top 5 --threshold 6 # Custom display
    python3 tools/spoke_expediter.py --spoke-path /other   # Different spoke
    python3 tools/spoke_expediter.py --dry-run             # Show decisions without writing
"""

import json
import os
import glob
import argparse
import hashlib
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from lug_utils import get_lug_id, get_lug_type, get_lug_status, get_lug_title, resolve_attribution
import wai_paths  # noqa: E402  harness-mode root resolver (single source of truth)


def _base(spoke_path):
    """Return the active working base (WAI-Spoke in v3; WAI-Harness/spoke/local in v4).
    Falls back to WAI-Spoke if no tree is detected (legacy behaviour unchanged)."""
    b, _ = wai_paths.resolve_wai_root(str(spoke_path))
    return b or os.path.join(str(spoke_path), "WAI-Spoke")


def _advisors_dir(spoke_path):
    """Return the advisors directory (sibling in v4: WAI-Harness/spoke/advisors;
    nested in v3: WAI-Spoke/advisors). Falls back to WAI-Spoke/advisors."""
    d = wai_paths.advisors_dir(str(spoke_path))
    return d or os.path.join(str(spoke_path), "WAI-Spoke", "advisors")


def now():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Lug Quality Scoring (10-point PEV rubric — matches hub Expediter)
# ---------------------------------------------------------------------------

SKIP_TYPES = {"epic", "e", "signal", "s", "idea", "policy", "audit", "directive", "session-summary",
              "report", "scout_report"}

def score_lug_quality(lug):
    """Score a lug on PEV completeness. Returns (score, missing_fields). Max: 10."""
    score = 0
    missing = []

    perceive = lug.get("perceive") or lug.get("p") or ""
    if len(str(perceive).strip()) > 10:
        score += 2
    else:
        missing.append("perceive")

    execute = lug.get("execute") or lug.get("e") or ""
    if len(str(execute).strip()) > 100:
        score += 2
    elif execute:
        score += 1
        missing.append("execute_too_vague")
    else:
        missing.append("execute")

    verify = lug.get("verify") or lug.get("v") or ""
    if len(str(verify).strip()) > 10:
        score += 2
    else:
        missing.append("verify")

    ac = lug.get("acceptance_criteria") or lug.get("ac") or []
    if isinstance(ac, list) and len(ac) > 0:
        score += 2
    else:
        missing.append("acceptance_criteria")

    tf = lug.get("target_files") or lug.get("tf") or []
    if isinstance(tf, list) and len(tf) > 0:
        score += 1
    else:
        missing.append("target_files")

    model_fit = (lug.get("model_fit") or lug.get("mf") or "").upper()
    if model_fit == "HAIKU":
        score += 1
    elif not model_fit:
        missing.append("model_fit_unset")

    return score, missing


def _num(val, default):
    """Coerce a possibly-non-numeric lug field (e.g. effort 'M') to float."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return float(default)


def get_roi(lug):
    """Extract ROI from lug. Compute as impact/effort if roi not present.
    Tolerant of non-numeric impact/effort (e.g. t-shirt sizes)."""
    roi = lug.get("roi")
    if roi is not None:
        return _num(roi, 1.0)
    impact = _num(lug.get("impact", 5), 5)
    effort = _num(lug.get("effort", lug.get("effort_score", 5)), 5)
    return impact / effort if effort > 0 else impact


def load_focus_lock_ids(spoke_path: str) -> set:
    """Return set of lug IDs belonging to any focus-locked active initiative."""
    focus_ids: set = set()
    idx_path = os.path.join(_base(spoke_path), "initiatives", "index.json")
    if not os.path.exists(idx_path):
        return focus_ids
    try:
        idx = json.load(open(idx_path))
    except (json.JSONDecodeError, OSError):
        return focus_ids
    active_states = {"approved", "active", "measuring"}
    for init in idx.get("initiatives", []):
        if not init.get("focus_lock"):
            continue
        if init.get("lifecycle_state", "proposed") not in active_states:
            continue
        for epic_id in init.get("epics", []):
            # Find epic file in bytype/epic/
            pattern = os.path.join(_base(spoke_path), "lugs", "bytype", "epic", "**", f"{epic_id}.json")
            for epic_path in glob.glob(pattern, recursive=True):
                try:
                    edata = json.load(open(epic_path))
                    for lug_id in edata.get("child_lugs", edata.get("impl_lugs", [])):
                        focus_ids.add(lug_id)
                except (json.JSONDecodeError, OSError):
                    pass
    return focus_ids


def suggest_improvements(lug, missing_fields):
    """Generate targeted improvement suggestions."""
    suggestions = []
    if "perceive" in missing_fields:
        suggestions.append("Add perceive: list specific files/state to read before starting")
    if "execute" in missing_fields:
        suggestions.append("Add execute: step-by-step instructions (3+ concrete steps)")
    elif "execute_too_vague" in missing_fields:
        suggestions.append("Expand execute: too brief — add specific commands/file edits")
    if "verify" in missing_fields:
        suggestions.append("Add verify: exact commands to confirm success")
    if "acceptance_criteria" in missing_fields:
        suggestions.append("Add acceptance_criteria: 2-4 testable conditions")
    if "target_files" in missing_fields:
        suggestions.append("Add target_files: exact file paths to create/modify")
    if "model_fit_unset" in missing_fields:
        suggestions.append("Set model_fit: HAIKU/SONNET/OPUS — cheapest capable model")
    elif (lug.get("model_fit") or "").upper() == "OPUS":
        suggestions.append("Review model_fit: can this be SONNET? Add specificity to push down")
    return suggestions


# ---------------------------------------------------------------------------
# Lug Scanning
# ---------------------------------------------------------------------------

def scan_lugs(spoke_path):
    """Scan active lugs (open + in_progress), skipping non-dispatchable types."""
    lugs = []
    for status in ("open", "in_progress"):
        pattern = os.path.join(_base(spoke_path), "lugs", "bytype", "*", status, "*.json")
        for filepath in glob.glob(pattern):
            try:
                with open(filepath) as f:
                    lug = json.load(f)
                lug["_filepath"] = filepath
                ty = get_lug_type(lug)
                if ty in SKIP_TYPES:
                    continue
                lugs.append(lug)
            except (json.JSONDecodeError, IOError):
                pass
    return lugs


# ---------------------------------------------------------------------------
# Signal Triage
# ---------------------------------------------------------------------------

SIGNAL_CATEGORIES = {
    "architectural": ["architecture", "design", "hub", "spoke", "advisor", "protocol", "schema",
                      "lug", "skill", "template", "migration", "canonical", "structure"],
    "operational": ["deploy", "cron", "nightly", "gardener", "tender", "health", "remediat",
                    "monitor", "uptime", "availability", "ci", "cd", "pipeline"],
    "ai-guidance": ["model", "haiku", "sonnet", "opus", "routing", "context", "token",
                    "prompt", "agent", "dispatch", "ozi", "claude", "gemini"],
    "performance": ["speed", "latency", "cache", "optim", "throughput", "cost", "efficient"],
    "security": ["auth", "permission", "secret", "encrypt", "sanitiz", "pii", "credential"],
    "workflow": ["session", "closeout", "wakeup", "teaching", "signal", "lug", "track",
                 "foundation", "process", "lifecycle"],
}

def categorize_signal(signal):
    """Assign a category based on keyword matching in title + signal + rationale."""
    text = " ".join([
        str(signal.get("title", "")),
        str(signal.get("signal", "")),
        str(signal.get("rationale", "")),
        str(signal.get("description", "")),
    ]).lower()

    scores = {}
    for category, keywords in SIGNAL_CATEGORIES.items():
        scores[category] = sum(1 for kw in keywords if kw in text)

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "reference"
    return best


def score_signal_quality(signal):
    """Score signal quality: 0-3 (has clear title + signal/description + rationale)."""
    score = 0
    if len(str(signal.get("title", "")).strip()) > 5:
        score += 1
    body = str(signal.get("signal", "") or signal.get("description", "")).strip()
    if len(body) > 20:
        score += 1
    if len(str(signal.get("rationale", "")).strip()) > 10:
        score += 1
    return score


def assess_scope(signal):
    """Assess signal scope: spoke-local, framework, hub, or multi-spoke."""
    text = " ".join([
        str(signal.get("title", "")),
        str(signal.get("signal", "")),
        str(signal.get("rationale", "")),
        str(signal.get("description", "")),
    ]).lower()

    if any(w in text for w in ["all spoke", "every spoke", "fleet", "cross-spoke", "multi-spoke"]):
        return "multi-spoke"
    if any(w in text for w in ["hub", "registry", "distribution", "kb pattern", "fleet"]):
        return "hub"
    if any(w in text for w in ["framework", "template", "teaching", "skill system", "protocol"]):
        return "framework"
    return "spoke-local"


def is_teaching_candidate(signal):
    """Does this signal encode a procedural rule that should become a teaching?"""
    text = " ".join([
        str(signal.get("signal", "")),
        str(signal.get("rationale", "")),
        str(signal.get("description", "")),
    ]).lower()
    rule_markers = ["always", "never", "must", "should", "rule", "pattern", "prevent",
                    "ensure", "enforce", "gate", "guard", "require"]
    return sum(1 for m in rule_markers if m in text) >= 2


def scan_signals(spoke_path):
    """Scan inbound signals (v2: WAI-Spoke/signals/inbound/)."""
    signals = []
    pattern = os.path.join(_base(spoke_path), "signals", "inbound", "*.json")
    for filepath in glob.glob(pattern):
        try:
            with open(filepath) as f:
                sig = json.load(f)
            sig["_filepath"] = filepath
            signals.append(sig)
        except (json.JSONDecodeError, IOError):
            pass
    return signals


def triage_signals(signals):
    """Triage signals: categorize, score quality, assess scope."""
    results = []
    for sig in signals:
        results.append({
            "id": get_lug_id(sig),
            "title": (get_lug_title(sig) or get_lug_id(sig))[:80],
            "impact": sig.get("impact", 0),
            "category": categorize_signal(sig),
            "quality": score_signal_quality(sig),
            "scope": assess_scope(sig),
            "teaching_candidate": is_teaching_candidate(sig),
            "filepath": sig.get("_filepath", ""),
            "triaged_at": now(),
        })
    results.sort(key=lambda x: (-x["impact"], -x["quality"]))
    return results


# ---------------------------------------------------------------------------
# Execution Mode Assignment (AP Routing)
# ---------------------------------------------------------------------------

def is_blocker_resolved(blocker_id, spoke_path):
    """Check if a blocker ID is resolved (file exists in bytype/*/open/)."""
    pattern = os.path.join(_base(spoke_path), "lugs", "bytype", "*", "open", f"{blocker_id}.json")
    matches = glob.glob(pattern)
    return len(matches) == 0  # Resolved if no file exists in open/


def find_sibling_lugs_by_parent(lug, all_open_lugs):
    """Find other lugs that share the same parent epic(s)."""
    parent_epics = lug.get("parent_epics") or []
    if not parent_epics:
        return []

    siblings = []
    for other_lug in all_open_lugs:
        if get_lug_id(other_lug) == get_lug_id(lug):
            continue
        other_parents = other_lug.get("parent_epics") or []
        if any(p in parent_epics for p in other_parents):
            siblings.append(other_lug)
    return siblings


def assign_execution_mode(lug, quality_score, all_open_lugs, spoke_path):
    """
    Determine execution_mode, execution_substrate, and gt_convoy_hint based on:
    - model_fit
    - quality_score
    - blocked_by field (verify each blocker is unresolved)
    - routed_to field
    - parent_epics (for gastown convoy context)

    Returns: (execution_mode, execution_substrate, gt_convoy_hint_or_None)
    """
    model_fit = (lug.get("model_fit") or lug.get("mf") or "").upper()
    routed_to = lug.get("routed_to") or "LOCAL"
    blocked_by = lug.get("blocked_by") or []

    # Check if any blocker is still unresolved
    unresolved_blockers = [b for b in blocked_by if not is_blocker_resolved(b, spoke_path)]

    # Decision table
    if unresolved_blockers:
        # Blocked by unresolved deps → tender
        hint = f"blocked: {', '.join(unresolved_blockers[:2])}"
        return ("tender", None, hint)

    if routed_to != "LOCAL":
        # Cross-spoke delivery required → subagent
        return ("subagent", None, f"cross-spoke delivery: routed_to={routed_to}")

    if model_fit == "HAIKU" and quality_score >= 7:
        # Haiku + quality>=7 + unblocked + LOCAL → gastown eligible
        execution_mode = "gastown"
        execution_substrate = "gastown"

        # Check for convoy hint (parent_epics with siblings)
        siblings = find_sibling_lugs_by_parent(lug, all_open_lugs)
        if siblings:
            parent_epics = lug.get("parent_epics") or []
            if parent_epics:
                epic_id = parent_epics[0]
                sibling_count = len(siblings)
                hint = f"convoy candidate: shares parent {epic_id} with {sibling_count} other lug(s) — sequence together"
                return (execution_mode, execution_substrate, hint)

        return (execution_mode, execution_substrate, None)

    if model_fit == "SONNET" and quality_score >= 6:
        # Sonnet + quality>=6 → subagent
        return ("subagent", None, None)

    if model_fit == "OPUS" or quality_score < 5:
        # Opus or quality<5 → tender
        reason = "opus" if model_fit == "OPUS" else f"quality={quality_score}"
        return ("tender", None, f"requires review: {reason}")

    # Default fallback: tender
    return ("tender", None, None)


# ---------------------------------------------------------------------------
# Work-availability manifest + hygiene scout + ready-queue matrix
# (spec-expediter-work-categorization-matrix-v1)
# ---------------------------------------------------------------------------

# Types that are never directly dispatchable by autopilot phase 3.
NONDISPATCH_TYPES = {"epic", "e", "signal", "s", "review", "session-summary", "spec",
                     "report", "scout_report"}
# Concrete lug types that represent ready value (the WORK row).
WORK_TYPES = {
    "implementation", "impl", "task", "t", "feature", "f", "bug", "b",
    "initiative_install", "rfc_response", "challenge_report",
    "harness-migration", "harness_migration",
}
# Markers that identify a scout job (the SCOUTING row).
SCOUT_MARKERS = ("hygiene_scout", "coverage_eval", "advisor_scout", "crew_provision")
# Core PEV fields; if any is missing a lug is NOT auto-groomable.
CORE_PEV_MISSING = {"perceive", "execute", "verify"}
# Drain priority across rows (CONFIRMED Mario 2026-06-03; sourced from
# tastegraph engagement-inbox-first: health->inbound->implementation->human refinement).
# health = the hygiene scout already run as flow step 1, so it is not a row here.
ROW_ORDER = {"teachings": 0, "work": 1, "scouting": 2, "refinement": 3, "triage": 4}

# Cost throttling: the FAST sort (score + categorize + route + emit ready-queue)
# is cheap and runs every time. The hygiene sweep is heavier (rglobs all lugs) and
# emits coverage-gap work that costs tokens downstream, so it only runs when the
# autonomous backlog is low (you are near the bottom and need replenishment) or
# periodically as a safety net — or when forced with --hygiene/--all.
HYGIENE_LOW_WATERMARK = 3   # run scout expedition when dispatchable autonomous work <= this
HYGIENE_STALE_DAYS = 7      # ...or when the last expedition is older than this
# A sweep also fires when an initiative is added/closed/reprioritized (fingerprint change).
# Cost is bounded structurally: one expedition report + at most one auto-refinement lug.


def count_dispatchable(scored):
    """Lugs that pass the autopilot dispatch filter (model set, not manual, not
    blocked, dispatchable type)."""
    return [
        s for s in scored
        if s.get("model_fit") and str(s.get("model_fit")).lower() != "unset"
        and str(s.get("execution_mode", "")).lower() != "manual"
        and not s.get("blocked")
        and (s.get("type") or "").lower() not in NONDISPATCH_TYPES
    ]


def _scan_state(advisor_dir):
    try:
        return json.load(open(os.path.join(advisor_dir, "scan_state.json")))
    except (json.JSONDecodeError, OSError):
        return {}


def _last_hygiene_at(advisor_dir):
    return _scan_state(advisor_dir).get("last_hygiene_at")


def initiatives_fingerprint(spoke_path):
    """Stable hash of the initiatives that would change priority: id +
    lifecycle_state + impact_rank. Adding, closing, or reprioritizing an
    initiative changes this fingerprint."""
    idx = os.path.join(_base(spoke_path), "initiatives", "index.json")
    try:
        d = json.load(open(idx))
    except (json.JSONDecodeError, OSError):
        return ""
    rows = sorted(
        (str(i.get("id")), str(i.get("lifecycle_state")), str(i.get("impact_rank", i.get("priority"))))
        for i in d.get("initiatives", [])
    )
    return hashlib.md5(json.dumps(rows).encode()).hexdigest()


def hygiene_due(advisor_dir, dispatchable_count, spoke_path, force=False):
    """Decide whether to run the (heavier) hygiene sweep this pass.
    Returns (bool, reason). Triggers: forced, low backlog, periodic, never-run,
    or an initiative was added/closed/reprioritized since the last sweep."""
    if force:
        return True, "forced (--hygiene/--all)"
    # Initiative add/close/reprioritize → full review (priorities just shifted).
    stored_fp = _scan_state(advisor_dir).get("initiatives_fingerprint")
    current_fp = initiatives_fingerprint(spoke_path)
    if stored_fp is not None and current_fp != stored_fp:
        return True, "initiative added/closed/reprioritized since last sweep"
    if dispatchable_count <= HYGIENE_LOW_WATERMARK:
        return True, f"backlog low ({dispatchable_count} <= {HYGIENE_LOW_WATERMARK} dispatchable)"
    last = _last_hygiene_at(advisor_dir)
    if not last:
        return True, "never run"
    try:
        dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days >= HYGIENE_STALE_DAYS:
            return True, f"periodic ({age_days}d >= {HYGIENE_STALE_DAYS}d since last sweep)"
    except (ValueError, TypeError):
        return True, "last_hygiene_at unparseable"
    return False, "fast sort only (backlog healthy, sweep recent)"


def _spoke_id(spoke_path):
    try:
        d = json.load(open(os.path.join(_base(spoke_path), "WAI-State.json")))
        w = d.get("wheel", {})
        return w.get("spoke_id") or d.get("wheel_id") or os.path.basename(spoke_path)
    except (json.JSONDecodeError, OSError):
        return os.path.basename(spoke_path)


def _hub_path(spoke_path):
    try:
        d = json.load(open(os.path.join(_base(spoke_path), "WAI-State.json")))
        return d.get("wheel", {}).get("hub_path")
    except (json.JSONDecodeError, OSError):
        return None


def _is_blocked(lug, spoke_path):
    for b in (lug.get("blocked_by") or []):
        if not is_blocker_resolved(b, spoke_path):
            return True
    return False


def _is_scout(lug):
    return any(lug.get(m) for m in SCOUT_MARKERS)


def is_auto_groomable(missing_fields):
    """A lug is auto-groomable only if it still has its core PEV bones."""
    return not (set(missing_fields or []) & CORE_PEV_MISSING)


def count_initiatives_active(spoke_path):
    idx = os.path.join(_base(spoke_path), "initiatives", "index.json")
    try:
        d = json.load(open(idx))
    except (json.JSONDecodeError, OSError):
        return 0
    active = {"approved", "active", "measuring"}
    return sum(
        1 for i in d.get("initiatives", [])
        if i.get("lifecycle_state", "proposed") in active
    )


def list_signals_undelivered(spoke_path):
    d = os.path.join(_base(spoke_path), "lugs", "bytype", "signal", "undelivered")
    if not os.path.isdir(d):
        return []
    return sorted(glob.glob(os.path.join(d, "*.json")))


def count_teachings_pending(spoke_path):
    """Best-effort: hub current teachings not yet in this spoke's processed dirs.
    Returns 0 on any path miss (never raises)."""
    hub = _hub_path(spoke_path)
    if not hub:
        return 0
    cur = None
    for cand in (
        os.path.join(hub, "teachings_repo", "spoke", "base", "teachings", "current"),
        os.path.join(hub, "framework", "teachings"),
    ):
        if os.path.isdir(cand):
            cur = cand
            break
    if not cur:
        return 0
    available = {os.path.basename(f) for f in glob.glob(os.path.join(cur, "*.teaching"))}
    processed = set()
    for sub in ("seed", "ingest", "processed"):
        pd = os.path.join(_base(spoke_path), "teachings", sub)
        if os.path.isdir(pd):
            processed |= {os.path.basename(f) for f in glob.glob(os.path.join(pd, "*"))}
    return len(available - processed)


def write_work_availability(spoke_path, scored, needs_refinement_count, spoke_id):
    """Emit WAI-Spoke/advisors/expediter/work-availability.json (counts summary).
    impl-expediter-work-availability-manifest-v1."""
    advisor_dir = os.path.join(_advisors_dir(spoke_path), "expediter")
    os.makedirs(advisor_dir, exist_ok=True)

    dispatchable_ids = [s["id"] for s in count_dispatchable(scored)]
    scout_pending = sum(1 for s in scored if s.get("scout"))
    signals_undelivered = len(list_signals_undelivered(spoke_path))
    initiatives_active = count_initiatives_active(spoke_path)
    teachings_pending = count_teachings_pending(spoke_path)

    summary = {
        "teachings_pending": teachings_pending,
        "initiatives_active": initiatives_active,
        "lugs_dispatchable": len(dispatchable_ids),
        "lugs_open_total": len(scored),
        "lugs_needs_refinement": needs_refinement_count,
        "scout_jobs_pending": scout_pending,
        "signals_undelivered": signals_undelivered,
    }
    has_work = any((
        teachings_pending, len(dispatchable_ids), scout_pending,
        signals_undelivered, initiatives_active,
    ))
    manifest = {
        "schema_version": "1.0",
        "spoke_id": spoke_id,
        "generated_at": now(),
        "has_work": has_work,
        "work_summary": summary,
        "dispatchable_lug_ids": dispatchable_ids,
        "skip_recommendation": not has_work,
        "skip_reason": None if has_work else "no dispatchable work",
    }
    path = os.path.join(advisor_dir, "work-availability.json")
    with open(path, "w") as f:
        f.write(json.dumps(manifest, indent=2))
    return manifest


def run_hygiene_scout(spoke_path, scored, trigger_reason="manual", dry_run=False):
    """Expediter scout expedition: chase each artifact's OWN declared expectations
    and verify they are satisfied — never invent work. An open lug declares its
    expectation via perceive/execute/verify + acceptance_criteria; a completed lug
    declares it via outcome_verification. Findings are unmet declared expectations.

    Output (cost-controlled):
      1. ONE expedition REPORT (what it ran + what it found) — a record, not work.
      2. If any finding is auto-groomable, ONE auto-refinement lug that processes the
         report and notifies the user (needs-you) ONLY for judgment-required findings.
    Returns a summary dict. spec-expediter-work-categorization-matrix-v1."""
    findings = []  # each: {target, expectation, evidence, auto_groomable}

    # Open lugs: expectation = "I declare a verifiable definition (PEV + acceptance)".
    for s in scored:
        missing = set(s.get("missing_fields", []))
        core_missing = sorted(missing & CORE_PEV_MISSING)
        expectation_missing = core_missing + (["acceptance_criteria"] if "acceptance_criteria" in missing else [])
        if not expectation_missing:
            continue
        # Auto-groomable when the core PEV bones exist (only soft fields missing).
        groomable = not (missing & CORE_PEV_MISSING)
        findings.append({
            "target": s["id"],
            "expectation": "declares a complete, verifiable definition (perceive/execute/verify + acceptance_criteria)",
            "evidence": f"missing: {', '.join(expectation_missing)}",
            "auto_groomable": groomable,
            # Provenance: the job that produced this artifact — work back here to
            # improve the producer so it stops emitting incomplete artifacts.
            "produced_by": s.get("produced_by", "unknown"),
            "source_spoke": s.get("source_spoke"),
            "target_created_at": s.get("target_created_at"),
        })

    # Completed lugs: expectation = "I recorded proof the goal was met (outcome_verification)".
    # REPORTED as a count only — never turned into per-item work (chasing the expected
    # path on hundreds of done lugs is noise, not backlog value).
    debt = {"deployed_unverified": 0, "spec_drift": 0, "abandoned": 0}
    try:
        _scripts = str(Path(__file__).parent.parent / "scripts")
        if _scripts not in sys.path:
            sys.path.insert(0, _scripts)
        import lug_debt_scanner as _lds
        _orig = _lds.LUGS_ROOT
        _lds.LUGS_ROOT = Path(_base(spoke_path)) / "lugs" / "bytype"
        try:
            res = _lds.scan_lugs()
        finally:
            _lds.LUGS_ROOT = _orig
        debt = {
            "deployed_unverified": len(res.get("deployed_unverified", [])),
            "spec_drift": len(res.get("spec_drift", [])),
            "abandoned": len(res.get("abandoned", [])),
        }
    except Exception as e:
        debt["error"] = str(e)

    # Canonical attribution for everything this expedition emits — who/when/where
    # in one string (session-...-{uuid8}.expediter-scout, kind=agent).
    scout_actor, scout_kind = resolve_attribution(spoke_path, agent="expediter-scout")

    groomable = [f for f in findings if f["auto_groomable"]]
    judgment = [f for f in findings if not f["auto_groomable"]]
    # Aggregate findings by the job that produced the artifact, so a producer that
    # repeatedly emits incomplete work stands out and can be improved at the source.
    by_producer = {}
    for f in findings:
        by_producer[f["produced_by"]] = by_producer.get(f["produced_by"], 0) + 1
    findings_by_producer = dict(sorted(by_producer.items(), key=lambda kv: kv[1], reverse=True))
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    report_id = f"scout-report-{ts}"
    refine_id = f"scout-refine-{ts}"

    report = {
        "id": report_id,
        "type": "scout_report",
        "status": "open",
        "title": f"Scout expedition report ({len(findings)} unmet expectations; trigger: {trigger_reason})",
        "routed_to": "LOCAL",
        "authored_by": scout_actor,
        "authored_kind": scout_kind,
        "created_at": now(),
        "scout_report": True,
        "trigger": trigger_reason,
        "scanned": {"open_lugs": len(scored), "findings": len(findings)},
        "principle": "Chase each artifact's declared expectation and verify it is satisfied. No invented work.",
        "findings": findings,
        "findings_by_producer": findings_by_producer,
        "verification_debt_reported": debt,
        "auto_refinement_lug": refine_id if groomable else None,
        "needs_user_judgment": [f["target"] for f in judgment],
    }

    refine_lug = None
    if groomable:
        refine_lug = {
            "id": refine_id,
            "type": "implementation",
            "status": "open",
            "title": f"Auto-refinement from {report_id}: satisfy {len(groomable)} declared expectations",
            "routed_to": "LOCAL",
            "model_fit": "haiku",
            "execution_mode": "auto",
            "urgency": 5,
            "effort_score": 2,
            "quality_score": 8,
            "initiative": "expediter-ready-queue",
            "authored_by": scout_actor,
            "authored_kind": scout_kind,
            "created_at": now(),
            "scout_refinement": True,
            "report_ref": report_id,
            "perceive": (
                f"Scout expedition {report_id} found {len(findings)} artifacts whose OWN declared "
                f"expectation is unmet. Refine the {len(groomable)} auto-groomable ones so each "
                f"satisfies what it already declares (do not invent new scope). "
                f"{len(judgment)} need human judgment — surface those, do not guess."
            ),
            "execute": [
                f"1. Read WAI-Spoke/advisors/expediter/expeditions/{report_id}.json — the findings list.",
                "2. For each finding with auto_groomable=true: open the target lug and complete the fields named in its evidence (perceive/execute/verify/acceptance_criteria) by making explicit what the lug already implies — chase the expected path, add no new scope.",
                "3. Re-run `python3 tools/spoke_expediter.py --spoke-path .` and confirm each refined target now passes the quality threshold.",
                "4. For findings under needs_user_judgment: write ONE concise needs-you note lug summarizing what decision is required (only if the list is non-empty). Do not fabricate a resolution. Include the report's findings_by_producer — if one job produced many incomplete artifacts, name it so the producing job can be improved at the source.",
                "5. Mark this lug complete with outcome_verification recording which targets were satisfied and which were escalated.",
            ],
            "verify": (
                f"Each auto_groomable target in {report_id} now passes score_lug_quality above threshold; "
                f"any judgment items produced a single needs-you note; no scope was invented."
            ),
            "acceptance_criteria": [
                "Every auto-groomable finding's declared expectation is now satisfied",
                "Judgment-required findings are surfaced to the user, not guessed",
                "outcome_verification records satisfied vs escalated targets",
            ],
        }

    summary = {
        "ts": now(),
        "scout": "expedition",
        "trigger": trigger_reason,
        "findings": len(findings),
        "auto_groomable": len(groomable),
        "needs_judgment": len(judgment),
        "verification_debt": debt,
        "findings_by_producer": findings_by_producer,
        "report_id": report_id,
        "refine_id": refine_id if groomable else None,
    }

    if not dry_run:
        advisor_dir = os.path.join(_advisors_dir(spoke_path), "expediter")
        exped_dir = os.path.join(advisor_dir, "expeditions")
        os.makedirs(exped_dir, exist_ok=True)
        # The expedition report (record of what ran + found).
        with open(os.path.join(exped_dir, f"{report_id}.json"), "w") as f:
            f.write(json.dumps(report, indent=2))
        # The single auto-refinement lug (turns findings into work; notifies if needed).
        # Dedup: if a prior scout-refine lug is still open/unprocessed, don't stack another.
        if refine_lug:
            open_dir = os.path.join(_base(spoke_path), "lugs", "bytype", "implementation", "open")
            existing = glob.glob(os.path.join(open_dir, "scout-refine-*.json"))
            if existing:
                summary["refine_id"] = os.path.splitext(os.path.basename(existing[0]))[0]
                summary["refine_dedup"] = True
            else:
                os.makedirs(open_dir, exist_ok=True)
                with open(os.path.join(open_dir, f"{refine_id}.json"), "w") as f:
                    f.write(json.dumps(refine_lug, indent=2))
        with open(os.path.join(advisor_dir, "runs.jsonl"), "a") as f:
            f.write(json.dumps(summary) + "\n")
    return summary


def _column_for(row, s):
    """Canonical-object-contract gate: autonomous only if the item passes its
    type's contract; otherwise needs-you."""
    if str(s.get("execution_mode", "")).lower() == "manual":
        return "needs-you"
    if (s.get("type") or "").lower() in NONDISPATCH_TYPES:
        return "needs-you"  # autopilot cannot dispatch these (spec/review/...) — human/Ozi handles
    if row == "triage":
        return "needs-you"
    if s.get("blocked"):
        return "needs-you"
    if row == "teachings":
        return "autonomous" if s.get("safe_to_auto_adopt") else "needs-you"
    if row == "work":
        has_model = s.get("model_fit") and str(s.get("model_fit")).lower() != "unset"
        return "autonomous" if (s["quality_score"] >= 6 and has_model) else "needs-you"
    if row == "refinement":
        return "autonomous" if s.get("auto_groomable") else "needs-you"
    if row == "scouting":
        return "autonomous"  # crew_provision recommendations are manual -> caught above
    return "needs-you"


def _row_for(s):
    ty = (s.get("type") or "").lower()
    if s.get("scout"):
        return "scouting"
    if ty in WORK_TYPES or ty == "spec":
        if s["quality_score"] <= s.get("_threshold", 6) and s.get("auto_groomable"):
            return "refinement"
        return "work"
    return "triage"  # unknown / leftover type -> catch-all


def build_work_queue(spoke_path, scored, threshold, spoke_id):
    """Build the 2x4 work-queue matrix (Autonomous/Attended x Teachings/Refinement/Work/Scouting).

    Uses validate_canonical as the completeness gate: lugs that FAIL validation
    with error severity go to Refinement; those that pass go to Work.
    Column rule: attended if model_fit in {sonnet,opus}, needs_attention=True,
    or blocked. Else autonomous.

    Returns the matrix dict (not written to disk -- see write_work_queue).
    """
    matrix = {
        "teachings": {"autonomous": [], "attended": []},
        "refinement": {"autonomous": [], "attended": []},
        "work": {"autonomous": [], "attended": []},
        "scouting": {"autonomous": [], "attended": []},
    }

    # Try to import validate_canonical for canonical pass/fail scoring.
    _validate_fn = None
    try:
        import importlib.util, sys as _sys
        _spec = importlib.util.spec_from_file_location(
            "validate_canonical",
            os.path.join(os.path.dirname(__file__), "validate_canonical.py")
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _validate_fn = _mod.run
    except Exception:
        pass

    # Build a set of lug ids with canonical errors (-> Refinement gate).
    canonical_error_ids = set()
    if _validate_fn:
        try:
            violations, _ = _validate_fn(spoke_path)
            for v in violations:
                if v.get("severity") == "error":
                    oid = v.get("object", "")
                    if oid:
                        canonical_error_ids.add(oid)
        except Exception:
            pass

    def _col(s):
        """autonomous if model_fit=haiku (or unset) + no flags; attended otherwise."""
        mf = str(s.get("model_fit", "haiku") or "haiku").lower()
        if mf in ("sonnet", "opus"):
            return "attended"
        if s.get("needs_attention") or s.get("blocked"):
            return "attended"
        if str(s.get("execution_mode", "")).lower() == "manual":
            return "attended"
        return "autonomous"

    for s in scored:
        ty = (s.get("type") or "").lower()
        lug_id = s.get("id", "")

        # Row: teachings
        if ty in ("teaching",) or s.get("safe_to_auto_adopt") is not None:
            col = "autonomous" if s.get("safe_to_auto_adopt") else "attended"
            matrix["teachings"][col].append(_item(s))
            continue

        # Row: scouting
        if s.get("scout") or ty in ("scout_report", "scouting"):
            col = _col(s)
            matrix["scouting"][col].append(_item(s))
            continue

        # Row: refinement vs work (canonical gate)
        is_refine = (
            lug_id in canonical_error_ids
            or s.get("needs_attention")
            or (s["quality_score"] <= threshold and s.get("auto_groomable"))
        )
        row = "refinement" if is_refine else "work"
        col = _col(s)
        matrix[row][col].append(_item(s))

    # Add pending teachings (from hub) as attended teachings
    teach_pending = count_teachings_pending(spoke_path)
    for _ in range(teach_pending):
        matrix["teachings"]["attended"].append({
            "id": "teaching-pending", "type": "teaching",
            "score": 0, "note": "pending adoption from hub"
        })

    counts = {
        row: {
            "autonomous": len(matrix[row]["autonomous"]),
            "attended": len(matrix[row]["attended"]),
        }
        for row in ("teachings", "refinement", "work", "scouting")
    }
    total_auto = sum(counts[r]["autonomous"] for r in counts)
    total_att = sum(counts[r]["attended"] for r in counts)

    return {
        "schema_version": "2.0",
        "spoke_id": spoke_id,
        "generated_at": now(),
        "priority_sequence": ["teachings", "refinement", "work", "scouting"],
        "matrix": matrix,
        "counts": counts,
        "totals": {"autonomous": total_auto, "attended": total_att},
    }


def _item(s):
    """Minimal item representation for work-queue entries."""
    return {
        "id": s.get("id", ""),
        "type": s.get("type", ""),
        "model_fit": s.get("model_fit", ""),
        "score": s.get("dispatch_priority", 0),
        "wave": s.get("wave", ""),
    }


def write_work_queue(spoke_path, work_queue):
    """Write the 2x4 work-queue matrix to advisors/expediter/work-queue.json."""
    advisor_dir = os.path.join(_advisors_dir(spoke_path), "expediter")
    os.makedirs(advisor_dir, exist_ok=True)
    path = os.path.join(advisor_dir, "work-queue.json")
    with open(path, "w") as f:
        f.write(json.dumps(work_queue, indent=2))
    return path


def write_ready_queue(spoke_path, scored, threshold, spoke_id):
    """Build the EXHAUSTIVE 2-column matrix over ALL work items and emit
    advisors/expediter/ready-queue.json. impl-expediter-readyqueue-matrix-v1.
    Ozi drains this: autonomous -> consumers, needs-you -> user."""
    advisor_dir = os.path.join(_advisors_dir(spoke_path), "expediter")
    os.makedirs(advisor_dir, exist_ok=True)

    rows = []
    # 1. Scored lugs (work / refinement / scouting / triage catch-all)
    for s in scored:
        s["_threshold"] = threshold
        s["auto_groomable"] = is_auto_groomable(s["missing_fields"])
        row = _row_for(s)
        col = _column_for(row, s)
        rows.append({
            "id": s["id"],
            "type": s.get("type"),
            "type_row": row,
            "column": col,
            "route": s.get("execution_mode"),
            "score": s.get("dispatch_priority", 0),
            "initiative_scoped": bool(s.get("initiative_scoped")),
        })
    # 2. Undelivered signals -> needs-you triage catch-all (exhaustiveness)
    for sig_path in list_signals_undelivered(spoke_path):
        rows.append({
            "id": os.path.splitext(os.path.basename(sig_path))[0],
            "type": "signal",
            "type_row": "triage",
            "column": "needs-you",
            "route": None,
            "score": 0,
            "initiative_scoped": False,
        })
    # 3. Teachings pending -> TEACHINGS row (count surfaced; needs-you by default)
    teach_pending = count_teachings_pending(spoke_path)
    if teach_pending:
        rows.append({
            "id": f"teachings-pending-{teach_pending}",
            "type": "teaching",
            "type_row": "teachings",
            "column": "needs-you",
            "route": None,
            "score": 0,
            "initiative_scoped": False,
            "note": f"{teach_pending} teaching(s) pending adoption; adopt before acting (inbox-first).",
        })

    # Sort within each column: ROW_ORDER, then initiative-scoped work first, then score.
    def _key(r):
        return (
            ROW_ORDER.get(r["type_row"], 9),
            0 if (r["type_row"] == "work" and r["initiative_scoped"]) else 1,
            -float(r.get("score") or 0),
        )

    autonomous = sorted([r for r in rows if r["column"] == "autonomous"], key=_key)
    needs_you = sorted([r for r in rows if r["column"] == "needs-you"], key=_key)

    ready_queue = {
        "schema_version": "1.0",
        "spoke_id": spoke_id,
        "generated_at": now(),
        "priority_sequence": ["teachings", "work(initiative-scoped first)", "scouting", "refinement", "triage"],
        "priority_source": "WAI-Spoke/tastegraph.json engagement-inbox-first",
        "columns": {
            "autonomous": autonomous,
            "needs_you": needs_you,
        },
        "display_labels": {"autonomous": "no-user-needed", "needs_you": "user-needed"},
        "counts": {
            "total": len(rows),
            "autonomous": len(autonomous),
            "needs_you": len(needs_you),
        },
    }
    # Exhaustiveness guarantee: every item categorized, nothing dropped.
    assert len(autonomous) + len(needs_you) == len(rows), "ready-queue dropped an item"

    path = os.path.join(advisor_dir, "ready-queue.json")
    with open(path, "w") as f:
        f.write(json.dumps(ready_queue, indent=2))
    return ready_queue


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Spoke-Local Expediter: Lug Quality + Signal Triage + AP Routing")
    parser.add_argument("--spoke-path", default=".", help="Path to spoke root (default: current dir)")
    parser.add_argument("--top", type=int, default=15, help="Number of top items to display")
    parser.add_argument("--threshold", type=int, default=6, help="Quality score threshold (<=N = needs refinement)")
    parser.add_argument("--signals", action="store_true", help="Also triage undelivered signals")
    parser.add_argument("--dry-run", action="store_true", help="Show routing decisions without writing to lug files")
    parser.add_argument("--hygiene", action="store_true", help="Run the hygiene/PEV scout (flow step 1): flag PEV/verification gaps + emit coverage-gap lugs")
    parser.add_argument("--all", action="store_true", help="Full Expediter flow: score + hygiene scout + signal triage + emit work-availability.json + ready-queue.json")
    parser.add_argument("--quiet", action="store_true", help="Suppress verbose display (still writes artifacts)")
    args = parser.parse_args()
    if args.all:
        args.signals = True
        args.hygiene = True

    spoke_path = os.path.abspath(args.spoke_path)
    advisor_dir = os.path.join(_advisors_dir(spoke_path), "expediter")
    os.makedirs(advisor_dir, exist_ok=True)

    print("Spoke Expediter — Lug Quality Scorer + Signal Triage")
    print(f"Spoke: {os.path.basename(spoke_path)}")
    print("=" * 70)

    # ── Lug Scoring ─────────────────────────────────────────────────────
    lugs = scan_lugs(spoke_path)
    print(f"\nLugs scanned: {len(lugs)} (excluding epics/signals/ideas)")

    focus_lock_ids = load_focus_lock_ids(spoke_path)
    if focus_lock_ids:
        print(f"Focus lock active: {len(focus_lock_ids)} lug(s) prioritized 3x")

    scored = []
    routing_summary = {"gastown": 0, "subagent": 0, "tender": 0}

    for lug in lugs:
        quality, missing = score_lug_quality(lug)
        roi = get_roi(lug)
        lug_id_for_focus = get_lug_id(lug)
        if focus_lock_ids and lug_id_for_focus in focus_lock_ids:
            roi = roi * 3.0
        elif focus_lock_ids:
            roi = roi * 0.5
        dispatch_priority = roi * (10 - quality)

        # Assign execution mode and routing
        exec_mode, exec_substrate, convoy_hint = assign_execution_mode(lug, quality, lugs, spoke_path)

        # Track routing counts
        if exec_mode in routing_summary:
            routing_summary[exec_mode] += 1

        # Write back to lug file (atomic: read-update-write)
        if not args.dry_run:
            filepath = lug.get("_filepath", "")
            if filepath and os.path.isfile(filepath):
                try:
                    with open(filepath, "r") as f:
                        lug_full = json.load(f)
                    # Update only the routing fields, preserve all others
                    lug_full["execution_mode"] = exec_mode
                    lug_full["execution_substrate"] = exec_substrate
                    if convoy_hint:
                        lug_full["gt_convoy_hint"] = convoy_hint
                    with open(filepath, "w") as f:
                        json.dump(lug_full, f, indent=2)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"  WARNING: Could not update {filepath}: {e}", file=sys.stderr)

        scored.append({
            "id": get_lug_id(lug),
            "title": (get_lug_title(lug) or get_lug_id(lug))[:80],
            "type": get_lug_type(lug),
            "quality_score": quality,
            "roi": round(roi, 2),
            "dispatch_priority": round(dispatch_priority, 2),
            "missing_fields": missing,
            "model_fit": (lug.get("model_fit") or lug.get("mf") or "unset"),
            "execution_mode": exec_mode,
            "execution_substrate": exec_substrate,
            "gt_convoy_hint": convoy_hint,
            "suggestions": suggest_improvements(lug, missing),
            "filepath": lug.get("_filepath", ""),
            "scored_at": now(),
            # Enrichment for manifest + ready-queue matrix categorization.
            "blocked": _is_blocked(lug, spoke_path),
            "scout": _is_scout(lug),
            "initiative_scoped": (lug_id_for_focus in focus_lock_ids) or bool(lug.get("initiative")),
            "safe_to_auto_adopt": bool(lug.get("safe_to_auto_adopt")),
            # Provenance — so a scout finding can name the job that produced this
            # artifact, to work back and improve that job.
            "produced_by": (lug.get("authored_by") or lug.get("source_spoke") or "unknown"),
            "source_spoke": lug.get("source_spoke"),
            "target_created_at": lug.get("created_at"),
        })

    scored.sort(key=lambda x: x["dispatch_priority"], reverse=True)
    needs_refinement = [s for s in scored if s["quality_score"] <= args.threshold]
    acceptable = [s for s in scored if s["quality_score"] > args.threshold]

    # Quality distribution
    dist = {}
    for s in scored:
        q = s["quality_score"]
        dist[q] = dist.get(q, 0) + 1
    print(f"\nQuality distribution:")
    for q in sorted(dist.keys()):
        bar = "█" * dist[q]
        label = "✗" if q <= args.threshold else "✓"
        print(f"  {q:2d}/10 {label} {bar} ({dist[q]})")
    print(f"\n  Needs refinement (≤{args.threshold}): {len(needs_refinement)}")
    print(f"  Acceptable (>{args.threshold}): {len(acceptable)}")

    # Write refinement queue
    queue_path = os.path.join(advisor_dir, "refinement-queue.jsonl")
    with open(queue_path, "w") as f:
        for item in scored:  # Write all scored items, sorted by priority
            f.write(json.dumps(item) + "\n")

    # ── Hygiene scout (heavier; throttled) ──────────────────────────────
    # FAST sort runs every time (score/categorize/route/emit below). The hygiene
    # sweep only runs when forced, when the backlog is low, or periodically —
    # because it emits coverage-gap work that costs tokens downstream.
    hygiene = None
    dispatchable_now = len(count_dispatchable(scored))
    do_hygiene, hyg_reason = hygiene_due(
        advisor_dir, dispatchable_now, spoke_path, force=(args.hygiene or args.all)
    )
    if do_hygiene:
        hygiene = run_hygiene_scout(spoke_path, scored, trigger_reason=hyg_reason, dry_run=args.dry_run)
        if not args.quiet:
            print(f"\nScout expedition [{hyg_reason}]: findings={hygiene['findings']} "
                  f"(auto_groomable={hygiene['auto_groomable']}, needs_judgment={hygiene['needs_judgment']}), "
                  f"verification_debt={hygiene['verification_debt']}, report={hygiene['report_id']}")
    elif not args.quiet:
        print(f"\nScout expedition: skipped — {hyg_reason}")

    # Display top targets
    top_n = min(args.top, len(needs_refinement))
    if top_n > 0:
        print(f"\nTop {top_n} refinement targets:")
        print(f"  {'ID':<42} {'ROI':>5} {'Q':>3} {'Pri':>7} {'Missing'}")
        print(f"  {'-'*80}")
        for item in needs_refinement[:top_n]:
            missing_str = ", ".join(item["missing_fields"][:3])
            print(f"  {item['id']:<42} {item['roi']:>5.1f} {item['quality_score']:>3} {item['dispatch_priority']:>7.1f}  {missing_str}")

    # ── Signal Triage ───────────────────────────────────────────────────
    signal_results = []
    if args.signals:
        signals = scan_signals(spoke_path)
        print(f"\n{'='*70}")
        print(f"Signal Triage: {len(signals)} undelivered signals")

        if signals:
            signal_results = triage_signals(signals)

            # Category summary
            cats = {}
            for s in signal_results:
                cats[s["category"]] = cats.get(s["category"], 0) + 1
            print(f"\nCategories: {', '.join(f'{c}={n}' for c, n in sorted(cats.items()))}")

            teaching_count = sum(1 for s in signal_results if s["teaching_candidate"])
            if teaching_count:
                print(f"Teaching candidates: {teaching_count}")

            print(f"\n  {'ID':<42} {'Impact':>6} {'Q':>3} {'Category':<15} {'Scope':<12} {'Teach'}")
            print(f"  {'-'*95}")
            for s in signal_results:
                teach = "→teach" if s["teaching_candidate"] else ""
                print(f"  {s['id']:<42} {s['impact']:>6} {s['quality']:>3} {s['category']:<15} {s['scope']:<12} {teach}")
        else:
            print("  No undelivered signals.")

    # ── Update State ────────────────────────────────────────────────────
    state_path = os.path.join(advisor_dir, "scan_state.json")
    if os.path.exists(state_path):
        with open(state_path) as f:
            state = json.load(f)
    else:
        state = {
            "advisor_id": "expediter",
            "advisor_name": "Spoke-Local Expediter",
            "version": "1.0.0",
            "initialized_at": now(),
            "stats": {},
        }

    state["last_run_at"] = now()
    state["refinement_queue_size"] = len(needs_refinement)
    # Always record the initiatives fingerprint so an add/close/reprioritize next
    # run is detected; record last_hygiene_at only when a sweep actually ran.
    state["initiatives_fingerprint"] = initiatives_fingerprint(spoke_path)
    if hygiene is not None and not args.dry_run:
        state["last_hygiene_at"] = now()
        state["last_hygiene_reason"] = hyg_reason
    stats = state.setdefault("stats", {})
    stats["lugs_scored"] = stats.get("lugs_scored", 0) + len(scored)
    stats["runs"] = stats.get("runs", 0) + 1
    stats["last_quality_avg"] = round(sum(s["quality_score"] for s in scored) / max(len(scored), 1), 1)
    stats["last_needs_refinement"] = len(needs_refinement)
    if signal_results:
        stats["signals_triaged"] = stats.get("signals_triaged", 0) + len(signal_results)
        stats["teaching_candidates_found"] = sum(1 for s in signal_results if s["teaching_candidate"])

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    # ── Work-availability manifest + ready-queue matrix + 2x4 work-queue ─
    # The Expediter is the single producer of the prioritized ready-queue.
    manifest = None
    ready_queue = None
    work_queue = None
    if not args.dry_run:
        spoke_id = _spoke_id(spoke_path)
        manifest = write_work_availability(spoke_path, scored, len(needs_refinement), spoke_id)
        ready_queue = write_ready_queue(spoke_path, scored, args.threshold, spoke_id)
        # 2x4 work-queue matrix: Autonomous/Attended x Teachings/Refinement/Work/Scouting
        # Uses validate_canonical as the Refinement<->Work gate.
        work_queue_data = build_work_queue(spoke_path, scored, args.threshold, spoke_id)
        write_work_queue(spoke_path, work_queue_data)
        work_queue = work_queue_data

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"EXPEDITER COMPLETE")
    print(f"  Lugs scored: {len(scored)}  |  Needs refinement: {len(needs_refinement)}  |  Avg quality: {stats['last_quality_avg']}/10")
    print(f"  Routed: {routing_summary['gastown']} gastown | {routing_summary['subagent']} subagent | {routing_summary['tender']} tender")
    print(f"  Mode: {'FULL (fast sort + scout expedition)' if hygiene else 'FAST sort only'} -- {hyg_reason}")
    if signal_results:
        print(f"  Signals triaged: {len(signal_results)}  |  Teaching candidates: {stats.get('teaching_candidates_found', 0)}")
    if hygiene:
        _ref = hygiene['refine_id'] or 'none'
        print(f"  Expedition: {hygiene['findings']} findings | report={hygiene['report_id']} | auto-refine={_ref} | notify-user={hygiene['needs_judgment']}")
        if hygiene.get('findings_by_producer'):
            _top = list(hygiene['findings_by_producer'].items())[:3]
            print(f"  Findings by producer: {', '.join(f'{p}={n}' for p, n in _top)}")
    if ready_queue:
        c = ready_queue["counts"]
        print(f"  Ready-queue: {c['total']} items -> {c['autonomous']} autonomous | {c['needs_you']} needs-you")
    if work_queue:
        t = work_queue["totals"]
        print(f"  Work-queue (2x4): autopilot-ready={t['autonomous']} | needs-you={t['attended']}")
    if manifest:
        print(f"  Work-availability: has_work={manifest['has_work']} | dispatchable={manifest['work_summary']['lugs_dispatchable']}")
    if args.dry_run:
        print(f"  DRY RUN: routing decisions shown above, lug files not modified")
    print(f"  Queue: {queue_path}")
    print(f"  State: {state_path}")


if __name__ == "__main__":
    main()
