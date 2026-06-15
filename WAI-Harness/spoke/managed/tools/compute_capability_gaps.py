#!/usr/bin/env python3
"""CapabilitiesGraph gap computer (spec-capabilitiesgraph-v1, gap_computation).

The CG bar (the resolved effective entries) is what the adopt/upgrade gap report
(AC31, AC46 capability-missing) is computed against. A gap is the diff between the
bar and what a survey actually found.

Rules (spec gap_computation):
  - mandated + absent                       -> BLOCKING (capability-missing)
  - mandated + present + uncertified (loose) -> BLOCKING (test-null)
  - mandated + requires_tools not all in the ToolGraph access_matrix -> BLOCKING (tool-missing)
  - recommended + absent + not declined     -> SOFT
  - recommended + declined                  -> not a gap (decision shown for transparency)
  - awareness + absent                       -> not a gap

The report is actionable, not just a list: it also emits a prioritized alignment
roadmap (mandated/blocking closers first, then recommended) — the value-prop
adopt scenario (project-wheelwright-value-prop).

Pure core: compute_capability_gaps(resolved_entries, survey, access_matrix=None).
"""
import argparse
import json
import sys


def compute_capability_gaps(resolved_entries, survey, access_matrix=None):
    """Diff the CG bar against a survey.

    resolved_entries: the effective CG entries (resolver output).
    survey: dict capability_id -> {"present": bool, "certified": bool}
            (a missing key is treated as absent). May also be a set/list of
            present-and-certified ids for the simple case.
    access_matrix: iterable of tool_ids available in the spoke ToolGraph; None
                   disables the tool-gate check.

    Returns {"blocking": [...], "soft": [...], "declined": [...], "roadmap": [...]}.
    Each gap: {capability, tier, type, reason, missing_tool?}.
    """
    if isinstance(survey, (set, list, tuple)):
        survey = {cid: {"present": True, "certified": True} for cid in survey}
    am = set(access_matrix) if access_matrix is not None else None

    blocking, soft, declined = [], [], []

    for e in resolved_entries:
        cid = e.get("id")
        tier = e.get("tier")
        status = e.get("status")
        s = survey.get(cid, {})
        present = bool(s.get("present"))
        certified = bool(s.get("certified"))
        requires = e.get("requires_tools") or []

        if tier == "mandated":
            # tool gate first (an inoperable capability is blocking regardless of presence)
            if am is not None and requires:
                missing = [t for t in requires if t not in am]
                if missing:
                    blocking.append({"capability": cid, "tier": tier, "type": "tool-missing",
                                     "missing_tool": missing,
                                     "reason": f"mandated capability requires tool(s) {missing} "
                                               "absent from the ToolGraph access_matrix"})
                    continue
            if not present:
                blocking.append({"capability": cid, "tier": tier, "type": "capability-missing",
                                 "reason": "mandated capability not implemented on this spoke"})
            elif not certified:
                blocking.append({"capability": cid, "tier": tier, "type": "test-null",
                                 "reason": "mandated capability present but uncertified (loose bolt)"})
        elif tier == "recommended":
            if status == "declined":
                declined.append({"capability": cid, "tier": tier,
                                 "reason": e.get("decision_rationale") or "declined (no rationale recorded)"})
            elif not present:
                soft.append({"capability": cid, "tier": tier, "type": "capability-missing",
                             "reason": "recommended capability absent (not declined)"})
            elif not certified:
                soft.append({"capability": cid, "tier": tier, "type": "test-null",
                             "reason": "recommended capability present but uncertified"})
        # awareness: never a gap

    # Alignment roadmap: mandated/blocking closers first, then recommended/soft.
    roadmap = []
    for g in blocking:
        roadmap.append({"priority": "P1-blocking", "capability": g["capability"],
                        "action": f"Close {g['type']} for mandated capability '{g['capability']}': {g['reason']}"})
    for g in soft:
        roadmap.append({"priority": "P2-recommended", "capability": g["capability"],
                        "action": f"Close {g['type']} for recommended capability '{g['capability']}': {g['reason']}"})

    return {"blocking": blocking, "soft": soft, "declined": declined, "roadmap": roadmap}


def main(argv):
    ap = argparse.ArgumentParser(description="Compute CapabilitiesGraph gaps vs a survey.")
    ap.add_argument("--effective", required=True, help="capabilities-effective.json (resolver output)")
    ap.add_argument("--survey", required=True, help="survey json: {cap_id: {present, certified}}")
    ap.add_argument("--access-matrix", default=None, help="json list of tool_ids (optional)")
    args = ap.parse_args(argv)

    eff = json.load(open(args.effective))
    entries = eff.get("entries", eff) if isinstance(eff, dict) else eff
    survey = json.load(open(args.survey))
    am = json.load(open(args.access_matrix)) if args.access_matrix else None

    r = compute_capability_gaps(entries, survey, am)
    print(json.dumps(r, indent=2))
    print(f"\n{len(r['blocking'])} blocking · {len(r['soft'])} soft · {len(r['declined'])} declined")
    return 1 if r["blocking"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
