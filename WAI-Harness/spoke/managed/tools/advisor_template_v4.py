#!/usr/bin/env python3
"""advisor_template_v4.py — the v4 advisor template model (AC15).

A v4 advisor declares more than a roster line: it owns files + data, runs on a schedule,
has an escalation path, keeps a patterns/ subfolder (ownership co-location), AND carries an
analysis_trigger that says WHEN it runs — observably (each evaluation is recorded to
scan_state so "why did/didn't it run" is answerable).

  validate_advisor_v4(defn)                 -> {ok, failures}: required v4 fields present + well-formed
  trigger_fires(analysis_trigger, signal_count, seconds_since_last) -> bool
       data_volume     : fires when signal_count >= threshold AND seconds_since_last >= floor (anti-thrash)
       time_since_last : fires when seconds_since_last >= max(threshold, floor)  (floor is the hard minimum)
  record_scan_state(path, advisor_id, fired, evidence, now_iso) -> append observable evaluation (jsonl)
  ensure_patterns_dir(advisor_root)         -> create the advisor's patterns/ subfolder

Pure + path-injected. The doc form lives in templates/commands/wai-advisor-schema.md (v4
section) + ADVISOR_TEMPLATE_v4.yaml; this module is the machine gate the advisor manager uses.
"""
import json
from pathlib import Path

REQUIRED_FIELDS = ("advisor_id", "owned_files", "owned_data", "schedule",
                   "escalation_path", "analysis_trigger")
TRIGGER_TYPES = {"data_volume", "time_since_last"}


def validate_advisor_v4(defn):
    """Return {ok, failures}. A v4 advisor must declare all REQUIRED_FIELDS, with a
    well-formed analysis_trigger {type in TRIGGER_TYPES, threshold:int>=0, minimum_floor_seconds:int>=0}."""
    failures = []
    for f in REQUIRED_FIELDS:
        if f not in defn or defn.get(f) in (None, "", [], {}):
            failures.append(f"advisor v4 field missing/empty: {f}")
    at = defn.get("analysis_trigger")
    if isinstance(at, dict):
        if at.get("type") not in TRIGGER_TYPES:
            failures.append(f"analysis_trigger.type {at.get('type')!r} not in {sorted(TRIGGER_TYPES)}")
        for k in ("threshold", "minimum_floor_seconds"):
            v = at.get(k)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                failures.append(f"analysis_trigger.{k} must be int>=0, got {v!r}")
    elif "analysis_trigger" not in [x for x in failures]:  # already flagged if missing
        if at is not None:
            failures.append("analysis_trigger must be an object")
    return {"ok": not failures, "failures": failures}


def trigger_fires(analysis_trigger, signal_count=0, seconds_since_last=None):
    """Evaluate whether the advisor should run now. seconds_since_last=None means it has
    never run (treated as +infinity so a floor/interval is satisfied)."""
    t = analysis_trigger.get("type")
    thr = int(analysis_trigger.get("threshold", 0))
    floor = int(analysis_trigger.get("minimum_floor_seconds", 0))
    elapsed = float("inf") if seconds_since_last is None else float(seconds_since_last)
    if t == "data_volume":
        return signal_count >= thr and elapsed >= floor      # volume met, but never thrash below floor
    if t == "time_since_last":
        return elapsed >= max(thr, floor)                    # floor is the hard minimum gap
    return False


def record_scan_state(path, advisor_id, fired, evidence, now_iso):
    """Append one observable trigger-evaluation record (jsonl). This is what makes
    'why did/didn't the advisor run' answerable after the fact."""
    rec = {"advisor_id": advisor_id, "ts": now_iso, "fired": bool(fired), "evidence": evidence}
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def ensure_patterns_dir(advisor_root):
    """Every v4 advisor co-locates a patterns/ subfolder (ownership). Idempotent."""
    d = Path(advisor_root) / "patterns"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)
