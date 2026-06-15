#!/usr/bin/env python3
"""reconcile_epic_acs.py - derive epic AC status from lug evidence (impl-derive-epic-ac-status-v1).

Epic acceptance_criteria_status is the one piece of the harness still ASSERTED by
hand (a [x]/[~]/[ ] checkbox mirror) rather than DERIVED from evidence the way
certification_score and coverage are. It drifts - in session-20260609-0713 four
sets of ACs were found mis-marked vs reality in a single session, dominantly
under-reporting, so every reader re-investigates already-done work.

This module diffs each epic AC's hand-written checkbox against the EVIDENCE - the
completed lugs that close it (via lug.closes_epic_acs) and their verification_test
results - and reports drift. It is THREE-valued, because a completed lug with a
green test can still only PARTIALLY close an AC (built-not-wired, delivered-not-
applied across a spoke boundary, mechanism-built-but-loop-not-live). A binary
"completed lug + green test => [x]" reconciler would false-promote those, re-
creating the over-flip it exists to prevent. So:

  evidence_status: full | partial | none
    full    = >=1 completed lug closes the AC with coverage=full AND a covering
              verification_test whose covers_ac names THIS AC has result==1 and is
              not stale (scope-correct + fresh).
    partial = a closing lug exists but is coverage=partial, OR its covering test is
              missing/failing/null/stale.
    none    = no completed lug closes the AC.

  drift_kind: none | under_report | over_report | mis_partial
    none         = checkbox matches evidence (done<->full, partial<->partial,
                   notstarted<->none).
    under_report = evidence full but the box is not [x] (the done-but-[ ] case).
    over_report  = evidence none but the box claims progress ([x] or [~]).
    mis_partial  = evidence partial but the box is [x] or [ ] (should be [~]).

SAFETY (P12): reconcile_acs PROPOSES verdicts and writes NOTHING. apply_reconciliation
APPENDS to epic.ac_reconciliations (audit trail, never overwrites a prior entry) and
the agent flips the box / sets [~] / justifies. It never auto-writes a checkbox and
never mutates a claimed/active or historical record.

Pure core: reconcile_acs(epic, lugs, now, freshness_days). read_ac_drift(spoke)
scans the lug+epic tree for the wakeup surface. CLI wraps with IO.
"""
import argparse
import glob
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wai_paths  # noqa: E402  harness-mode-aware path resolver

DEFAULT_FRESHNESS_DAYS = 30

_CHECKBOX = re.compile(r"^\s*\[([x~ ])\]\s*(AC\d+)?", re.IGNORECASE)
_CHECKBOX_STATUS = {"x": "done", "~": "partial", " ": "notstarted"}

# drift classification: (checkbox_status, evidence_status) -> drift_kind
_DRIFT = {
    ("done", "full"): "none",
    ("done", "partial"): "mis_partial",
    ("done", "none"): "over_report",
    ("partial", "full"): "under_report",
    ("partial", "partial"): "none",
    ("partial", "none"): "over_report",
    ("notstarted", "full"): "under_report",
    ("notstarted", "partial"): "mis_partial",
    ("notstarted", "none"): "none",
}


def _ac_token(s):
    """Leading 'ACn' token of an AC string / id, uppercased; '' if none."""
    if not s:
        return ""
    m = re.search(r"AC\d+", str(s), re.IGNORECASE)
    return m.group(0).upper() if m else ""


def _parse_ts(s):
    if isinstance(s, (int, float)):
        return float(s)
    if not s or not isinstance(s, str):
        return None
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def parse_ac(ac_string):
    """('[x] AC8 ...') -> (checkbox_status, ac_id, text). Unparseable -> (None, '', text)."""
    s = str(ac_string)
    m = _CHECKBOX.match(s)
    if not m:
        return None, _ac_token(s), s.strip()
    status = _CHECKBOX_STATUS.get(m.group(1).lower())
    ac_id = (m.group(2) or "").upper() or _ac_token(s)
    return status, ac_id, s.strip()


def _test_fresh(test, lug, now, freshness_days):
    """A covering test is fresh unless we can prove it stale: if a timestamp is
    available (test.result_ts / verified_at, else lug.completed_at) and older than
    the window, it is stale. Absent timestamp -> fresh (benefit of the doubt)."""
    ts = _parse_ts(test.get("result_ts") or test.get("verified_at")
                   or test.get("verified_by") or lug.get("completed_at"))
    if ts is None:
        return True
    return (now - ts) <= freshness_days * 86400


def _closing_entries(ac_id, lugs, epic_id=None):
    """All (lug, coverage, pending) where a COMPLETED lug closes ac_id via
    closes_epic_acs (string entry = sugar for coverage:full).

    EPIC-SCOPED (collision guard): AC ids are unique only WITHIN an epic — v3 and v4
    both have an 'AC1'. A lug's entry credits epic_id ONLY if its scope matches:
    entry['epic'] if the entry names one, else the lug's parent_epic. Without this,
    a lug closing v4 AC1 would also credit v3 AC1 (observed S45). epic_id=None keeps
    the legacy global match (back-compat for single-epic callers)."""
    out = []
    for lug in lugs:
        if lug.get("status") != "completed":
            continue
        for entry in lug.get("closes_epic_acs") or []:
            if isinstance(entry, str):
                ac_field, cov, pending, entry_epic = entry, "full", None, None
            elif isinstance(entry, dict):
                ac_field = entry.get("ac", "")
                cov = entry.get("coverage", "full")
                pending = entry.get("pending")
                entry_epic = entry.get("epic")
            else:
                continue
            if _ac_token(ac_field) != ac_id:
                continue
            # Epic scope: exclude ONLY on a positive mismatch. A lug whose scope
            # (entry.epic, else parent_epic) names a DIFFERENT epic does not credit
            # this one (collision guard). A lug with no scope falls back to the
            # legacy global token match (back-compat for single-epic callers/fixtures).
            if epic_id is not None:
                scope = entry_epic or lug.get("parent_epic") or lug.get("epic")
                if scope is not None and scope != epic_id:
                    continue
            out.append((lug, cov, pending))
    return out


def evidence_for(ac_id, lugs, now, freshness_days=DEFAULT_FRESHNESS_DAYS, epic_id=None):
    """Return (evidence_status, closing_lug_ids, pending[]) for one AC of epic_id."""
    closing = _closing_entries(ac_id, lugs, epic_id)
    if not closing:
        return "none", [], []
    pendings = []
    has_full = False
    for lug, cov, pending in closing:
        if cov == "partial":
            if pending:
                pendings.append(pending)
            continue
        # coverage:full claimed -> require a scope-correct, green, fresh covering test
        green = False
        for t in lug.get("verification_test") or []:
            if _ac_token(t.get("covers_ac", "")) != ac_id:   # scope guard: no sibling credit
                continue
            if t.get("result") != 1:
                continue
            if not _test_fresh(t, lug, now, freshness_days):
                continue
            green = True
            break
        if green:
            has_full = True
        else:
            pendings.append(
                f"{lug.get('id')}: coverage:full claimed but covering test for "
                f"{ac_id} is missing / not-green / stale")
    status = "full" if has_full else "partial"
    return status, [l.get("id") for l, _, _ in closing], pendings


def classify_drift(checkbox_status, evidence_status):
    if checkbox_status is None:
        return "unparsed"
    return _DRIFT.get((checkbox_status, evidence_status), "none")


def reconcile_acs(epic, lugs, now=None, freshness_days=DEFAULT_FRESHNESS_DAYS):
    """Diff each epic AC checkbox against lug evidence. PROPOSES; writes nothing.

    Returns a list of verdicts:
      {ac, checkbox_status, evidence_status, closing_lugs, pending,
       drift (bool), drift_kind, proposed_checkbox}
    """
    if now is None:
        now = time.time()
    now = _parse_ts(now) if isinstance(now, str) else float(now)
    acs = epic.get("acceptance_criteria_status") or epic.get("acceptance_criteria") or []
    verdicts = []
    for ac_string in acs:
        checkbox, ac_id, text = parse_ac(ac_string)
        if not ac_id:
            verdicts.append({"ac": text, "checkbox_status": checkbox,
                             "evidence_status": None, "drift": False,
                             "drift_kind": "unparsed", "closing_lugs": [],
                             "pending": [], "proposed_checkbox": None})
            continue
        evidence, closing, pending = evidence_for(
            ac_id, lugs, now, freshness_days, epic_id=epic.get("id"))
        kind = classify_drift(checkbox, evidence)
        proposed = {"full": "[x]", "partial": "[~]", "none": "[ ]"}[evidence]
        verdicts.append({
            "ac": ac_id,
            "text": text,
            "checkbox_status": checkbox,
            "evidence_status": evidence,
            "closing_lugs": closing,
            "pending": pending,
            "drift": kind not in ("none", "unparsed"),
            "drift_kind": kind,
            "proposed_checkbox": proposed,
        })
    return verdicts


def drift_summary(verdicts):
    """Count by drift_kind for the wakeup surface."""
    out = {"under_report": 0, "over_report": 0, "mis_partial": 0, "total_drift": 0}
    for v in verdicts:
        k = v["drift_kind"]
        if k in out:
            out[k] += 1
        if v["drift"]:
            out["total_drift"] += 1
    return out


def apply_reconciliation(epic, verdicts, applied_by="unknown", now_iso=None):
    """APPEND a reconciliation record to epic.ac_reconciliations (audit, never
    overwrite). Returns a NEW epic dict; does not write to disk and does not flip a
    single checkbox (the agent does that, or justifies). Refuses to touch a record
    that is not an open/in_progress epic (P12: no claimed/active/historical mutation).
    """
    status = epic.get("status")
    if status not in ("open", "in_progress", None):
        raise ValueError(
            f"refusing to reconcile an epic with status={status!r} "
            "(P12: never mutate a claimed/active or historical record)")
    now_iso = now_iso or datetime.now(timezone.utc).isoformat()
    record = {
        "applied_at": now_iso,
        "applied_by": applied_by,
        "summary": drift_summary(verdicts),
        "drifting_acs": [
            {"ac": v["ac"], "drift_kind": v["drift_kind"],
             "checkbox_status": v["checkbox_status"],
             "evidence_status": v["evidence_status"],
             "proposed_checkbox": v["proposed_checkbox"],
             "closing_lugs": v["closing_lugs"], "pending": v["pending"]}
            for v in verdicts if v["drift"]
        ],
    }
    new_epic = dict(epic)
    history = list(new_epic.get("ac_reconciliations") or [])
    history.append(record)               # append-only; prior entries untouched
    new_epic["ac_reconciliations"] = history
    return new_epic


# --- spoke scans ------------------------------------------------------------

def _spoke(spoke_path):
    """Resolve the active working base by harness mode: v3 -> <root>/WAI-Spoke,
    v4-only -> <root>/WAI-Harness/spoke/local. Hardcoding WAI-Spoke made this
    silently scan a non-existent path (no drift found) on a v4-only spoke
    post-v3-retirement (cutover-blocker I-5)."""
    p = Path(spoke_path)
    if p.name == "WAI-Spoke":
        return p
    base, _ = wai_paths.resolve_wai_root(str(p))
    return Path(base) if base else (p / "WAI-Spoke")


def _load_all_lugs(spoke):
    lugs = []
    for f in glob.glob(str(spoke / "lugs" / "bytype" / "**" / "*.json"), recursive=True):
        try:
            lugs.append(json.load(open(f)))
        except (OSError, json.JSONDecodeError):
            continue
    return lugs


def _load_open_epics(spoke):
    epics = []
    for status in ("open", "in_progress"):
        for f in sorted(glob.glob(str(spoke / "lugs" / "bytype" / "epic" / status / "*.json"))):
            try:
                epics.append(json.load(open(f)))
            except (OSError, json.JSONDecodeError):
                continue
    return epics


def read_ac_drift(spoke_path=".", now=None, freshness_days=DEFAULT_FRESHNESS_DAYS):
    """Wakeup surface: {epic_id: {under_report, over_report, mis_partial, total_drift}}
    for every open epic. Degrades gracefully (empty dict) if nothing scans."""
    try:
        spoke = _spoke(spoke_path)
        lugs = _load_all_lugs(spoke)
        out = {}
        for epic in _load_open_epics(spoke):
            verdicts = reconcile_acs(epic, lugs, now=now, freshness_days=freshness_days)
            out[epic.get("id")] = drift_summary(verdicts)
        return out
    except Exception:
        return {}


def has_unresolved_drift(spoke_path=".", now=None):
    """Closeout gate helper: True if any open epic has AC drift vs evidence."""
    drift = read_ac_drift(spoke_path, now=now)
    return any(d.get("total_drift", 0) > 0 for d in drift.values())


def main(argv):
    ap = argparse.ArgumentParser(description="Reconcile epic AC checkboxes against lug evidence.")
    ap.add_argument("--spoke-path", default=".")
    ap.add_argument("--epic", default=None, help="epic id (default: all open epics)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--drift-only", action="store_true", help="print only drifting ACs")
    args = ap.parse_args(argv)

    spoke = _spoke(args.spoke_path)
    lugs = _load_all_lugs(spoke)
    epics = _load_open_epics(spoke)
    if args.epic:
        epics = [e for e in epics if e.get("id") == args.epic]
        if not epics:
            print(f"epic {args.epic} not found among open epics", file=sys.stderr)
            return 1

    report = {}
    for epic in epics:
        verdicts = reconcile_acs(epic, lugs)
        report[epic.get("id")] = {"summary": drift_summary(verdicts), "verdicts": verdicts}

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    for epic_id, data in report.items():
        s = data["summary"]
        print(f"\n{epic_id}: {s['total_drift']} drift "
              f"(under={s['under_report']} over={s['over_report']} mis_partial={s['mis_partial']})")
        for v in data["verdicts"]:
            if args.drift_only and not v["drift"]:
                continue
            flag = "" if not v["drift"] else f"  <<< {v['drift_kind']} -> propose {v['proposed_checkbox']}"
            print(f"  {v['ac']}: box={v['checkbox_status']} evidence={v['evidence_status']}{flag}")
            if v["pending"]:
                for p in v["pending"]:
                    print(f"      pending: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
