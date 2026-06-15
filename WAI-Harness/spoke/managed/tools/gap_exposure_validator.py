#!/usr/bin/env python3
"""gap_exposure_validator.py — gap-taxonomy exposure + survey completeness (AC46).

verification_spine.GAP_TYPES already defines the 7-type taxonomy (test-null, ac-uncovered,
path-untested, capability-missing, decision-undocumented, cruft/misplacement, deprecation-live)
with a detector + surface per type. This closes AC46's SECOND half:

  1. Every gap is EXPOSED on its declared surface — a gap of an unknown type, or a deficiency
     not raised as a typed gap, is "gap-hidden" (rejected). No silent gaps.
  2. A dropped/closed-without-AC lug MUST log a reason (closes_no_ac or decision_rationale),
     else it is gap-hidden (a silently-dropped deficiency).
  3. Survey completeness: the Historian survey's file manifest is audited against the
     CapabilitiesGraph bar — orphan files, untested capabilities, and unscanned categories
     become typed gaps, yielding a coverage_pct.

Pure + path-injected; reuses verification_spine.GAP_TYPES so the taxonomy stays single-source.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
try:
    import verification_spine as _vs
    GAP_TYPES = _vs.GAP_TYPES
except Exception:  # noqa: BLE001 — keep usable standalone
    GAP_TYPES = {
        "test-null": {"detector": "QA/coverage", "surface": "Quality Health null rate"},
        "ac-uncovered": {"detector": "lug-reviewer", "surface": "test-at-birth gate"},
        "path-untested": {"detector": "QA + GitNexus", "surface": "Quality Health coverage %"},
        "capability-missing": {"detector": "Aimer vs CapabilitiesGraph", "surface": "adoption gap report"},
        "decision-undocumented": {"detector": "Historian", "surface": "survey gap list"},
        "cruft/misplacement": {"detector": "Historian/Asset-Reviewer", "surface": "Hygiene adoption-correctness"},
        "deprecation-live": {"detector": "self-healing AC22 + Trainer", "surface": "stale-write trend"},
    }


def classify_gap(gap_type):
    """Return {detector, surface} for a known gap type, or None if unknown (gap-hidden)."""
    return GAP_TYPES.get(gap_type)


def validate_gap_exposure(gaps):
    """Every gap must carry a recognized gap_type that maps to a surface. A gap with an
    unknown/absent type is gap-hidden. Returns {ok, exposed:[...], hidden:[...]}."""
    exposed, hidden = [], []
    for g in gaps:
        meta = classify_gap(g.get("gap_type"))
        if meta:
            exposed.append({**g, "surface": meta["surface"], "detector": meta["detector"]})
        else:
            hidden.append({**g, "reason": "unknown/absent gap_type — no surface to expose on"})
    return {"ok": not hidden, "exposed": exposed, "hidden": hidden}


def validate_dropped_lugs(lugs):
    """A lug that closes no acceptance criterion MUST log WHY (closes_no_ac or a non-empty
    decision_rationale). One that doesn't is a silently-dropped deficiency = gap-hidden.
    Returns {ok, hidden:[lug_id,...]}."""
    hidden = []
    for lug in lugs:
        closes = lug.get("closes_epic_acs") or lug.get("acceptance_criteria") or []
        if closes:
            continue  # it closes ACs — not a drop
        has_reason = bool(lug.get("closes_no_ac")) or bool((lug.get("decision_rationale") or "").strip())
        if not has_reason:
            hidden.append(lug.get("id", "<no-id>"))
    return {"ok": not hidden, "hidden": hidden}


def survey_completeness(manifest_files, cg_entries, trash_prefixes=("trash_bin/",)):
    """Audit a Historian survey file-manifest against the CapabilitiesGraph bar.

    manifest_files: list of {path, tested(bool)} the survey found in the codebase.
    cg_entries: resolved CG entries (each may carry file_paths + verification_ref).

    Produces typed gaps:
      - cruft/misplacement : a file on disk claimed by no CG entry (and not trash)
      - test-null          : a CG entry whose file exists but has no verification_ref
      - path-untested      : a manifest file mapped to the CG but tested=False
    coverage_pct = files that are home-mapped AND tested / total non-trash files.
    Returns {coverage_pct, gaps:[...], orphans:[...], total}.
    """
    cg_paths = set()
    untested_caps = []
    for e in cg_entries:
        fps = e.get("file_paths", []) or []
        cg_paths.update(fps)
        if fps and not (e.get("verification_ref")):
            untested_caps.append(e.get("id") or fps[0])

    gaps, orphans, mapped_tested = [], [], 0
    non_trash = [f for f in manifest_files
                 if not any(f["path"].startswith(p) for p in trash_prefixes)]
    for f in non_trash:
        path = f["path"]
        mapped = path in cg_paths
        if not mapped:
            orphans.append(path)
            gaps.append({"gap_type": "cruft/misplacement", "path": path,
                         "detail": "file on disk not claimed by any CG entry"})
        elif not f.get("tested"):
            gaps.append({"gap_type": "path-untested", "path": path,
                         "detail": "CG-mapped file has no passing test"})
        else:
            mapped_tested += 1
    for cap in untested_caps:
        gaps.append({"gap_type": "test-null", "capability": cap,
                     "detail": "CG capability has no verification_ref"})

    total = len(non_trash)
    coverage = round(100.0 * mapped_tested / total, 1) if total else 100.0
    # every produced gap must be exposable on a surface
    exposure = validate_gap_exposure(gaps)
    return {"coverage_pct": coverage, "total": total, "orphans": orphans,
            "gaps": gaps, "exposure_ok": exposure["ok"], "hidden_gaps": exposure["hidden"]}
