"""Validate WAI objects against the Canonical Object Contract.

The contract is data, not code: it lives in
  WAI-Spoke/lugs/bytype/spec/active/spec-canonical-object-contract-v1.json
and this validator enforces it. Define once, enforce everywhere — so the
expectations are maintained as the harness evolves instead of re-derived.

Four dimensions per object: behavior, completeness, cross-linking, flow.

Usage:
  python3 tools/validate_canonical.py [--spoke-path .] [--json] [--strict]
  python3 tools/validate_canonical.py --track <path/to/track.jsonl> [--json]

Track mode validates a session track file:
  - Valid JSONL (0 parse errors)
  - session_start entry present
  - Exactly ONE terminal closeout as the last entry
  - Every turn entry has attribution (contributor, kind, origin_session_id)
    AND content (assistant_text or tools_used)
  - No entries after the terminal closeout

Exit code: 0 if no error-severity violations, 1 otherwise (warn-only passes).
A violation is {object, dimension, rule, severity, detail}.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SPEC_REL = "WAI-Spoke/lugs/bytype/spec/active/spec-canonical-object-contract-v1.json"
OPEN_STATUSES = {"open", "o"}
INPROGRESS_STATUSES = {"in-progress", "in_progress", "p"}
DONE_STATUSES = {"closed", "resolved", "c", "done", "completed"}
MODEL_FITS = {"haiku", "sonnet", "opus"}


def _load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _all_lug_ids(spoke):
    """Every lug id known to the spoke (any type/status) — for cross-link resolution."""
    ids = set()
    for f in (spoke / "WAI-Spoke/lugs").rglob("*.json"):
        d = _load_json(f)
        if isinstance(d, dict):
            lid = d.get("id") or d.get("i")
            if lid:
                ids.add(lid)
    return ids


def _active_spec_ids(spoke):
    ids = set()
    for f in (spoke / "WAI-Spoke/lugs/bytype/spec/active").glob("*.json"):
        d = _load_json(f)
        if isinstance(d, dict) and d.get("id"):
            ids.add(d["id"])
    return ids


def _nonempty(v):
    if v is None:
        return False
    if isinstance(v, (list, dict, str)):
        return len(v) > 0
    return True


def validate_lug(path, lug, rules, spoke, lug_ids, spec_ids):
    """Yield violations for one lug against the contract's 'lug' rules."""
    oid = lug.get("id") or lug.get("i") or path.name
    ltype = lug.get("type") or lug.get("ty") or "?"
    status = str(lug.get("status") or lug.get("s") or "").lower()
    V = lambda dim, rule, sev, detail: {
        "object": oid, "path": str(path), "dimension": dim,
        "rule": rule, "severity": sev, "detail": detail}

    # SCOPE — the lug contract governs actionable lug types only. Other artifacts
    # (signal, session-summary, foundation, autosave, notice, challenge-report)
    # are out of scope for v1; the contract can be extended to them later.
    applies = set(rules.get("applies_to_types", []))
    if applies and ltype not in applies:
        return

    # COMPLETENESS — required fields
    for f in rules.get("required_fields", []):
        if not _nonempty(lug.get(f)):
            yield V("completeness", "required_field", "error", f"missing '{f}'")

    title = lug.get("title") or lug.get("t") or ""
    if len(str(title)) < 10:
        yield V("completeness", "title_min_len", "error", f"title <10 chars: {title!r}")

    # Lifecycle-aware severity: PEV gaps block actionable (open/in-progress) lugs,
    # but on completed/historical lugs they are warn-level hygiene, not a gate failure.
    pev_sev = "warn" if status in DONE_STATUSES else "error"
    exempt = set(rules.get("exempt_types_from_pev", []))
    if ltype not in exempt:
        perceive = lug.get("perceive")
        execute = lug.get("execute")
        verify = lug.get("verify") or lug.get("acceptance_criteria")
        if not _nonempty(perceive):
            yield V("completeness", "non_empty", pev_sev, "perceive empty")
        if not _nonempty(execute):
            yield V("completeness", "non_empty", pev_sev, "execute empty")
        if not _nonempty(verify):
            yield V("behavior", "has_pev", pev_sev, "no verify or acceptance_criteria")

    mf = lug.get("model_fit")
    if mf and str(mf).lower() not in MODEL_FITS:
        yield V("completeness", "model_fit_enum", "error", f"bad model_fit: {mf}")
    if ltype == "implementation" and not mf:
        yield V("behavior", "model_fit_required", "error", "implementation lug missing model_fit")

    effort = lug.get("effort_score", lug.get("effort"))
    if effort is not None:
        try:
            if not (1 <= int(effort) <= 5):
                yield V("completeness", "effort_range", "warn", f"effort {effort} outside 1-5")
        except (TypeError, ValueError):
            yield V("completeness", "effort_range", "warn", f"effort not numeric: {effort}")

    # COMPLETENESS — referenced files exist (warn)
    for field in ("target_files", "files_to_read", "files_to_edit"):
        for ref in lug.get(field, []) or []:
            rel = str(ref).split(" ")[0]
            if rel and not (spoke / rel).exists() and not Path(rel).exists():
                yield V("completeness", "referenced_files_exist", "warn",
                        f"{field} -> missing file {rel}")

    # CROSS-LINKING — ids resolve
    for field in ("dependencies", "blocked_by", "blocking"):
        for ref in lug.get(field, []) or []:
            if ref and ref not in lug_ids:
                yield V("cross_linking", "ids_resolve", "warn",
                        f"{field} -> unknown lug id {ref}")
    spec_id = lug.get("spec_id")
    if spec_id and spec_id not in spec_ids:
        yield V("cross_linking", "spec_resolves", "warn",
                f"spec_id -> no active spec {spec_id}")

    # FLOW — folder matches status
    parent = path.parent.name
    if parent == "open" and status and status not in OPEN_STATUSES:
        yield V("flow", "folder_matches_status", "error",
                f"in open/ but status={status}")
    if parent == "in_progress" and status and status not in INPROGRESS_STATUSES:
        yield V("flow", "folder_matches_status", "error",
                f"in in_progress/ but status={status}")
    if parent == "completed":
        if status and status not in DONE_STATUSES:
            yield V("flow", "folder_matches_status", "error",
                    f"in completed/ but status={status}")
        if not any(_nonempty(lug.get(k)) for k in
                   ("outcome_verification", "verify_result", "completed_at")):
            yield V("flow", "completed_has_verification", "warn",
                    "completed lug records no verification/completed_at")


def validate_track(track_path):
    """Validate a session track.jsonl file for quality and structural integrity.

    Returns a list of violations in the same format as validate_lug.
    """
    track_path = Path(track_path)
    violations = []
    V = lambda rule, sev, detail: {
        "object": track_path.name, "path": str(track_path),
        "dimension": "track", "rule": rule, "severity": sev, "detail": detail}

    if not track_path.exists():
        return [V("file_exists", "error", f"track file not found: {track_path}")]

    # Parse JSONL — collect parse errors
    rows = []
    raw_lines = track_path.read_text().splitlines()
    parse_errors = 0
    for i, line in enumerate(raw_lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            violations.append(V("valid_jsonl", "error",
                                f"line {i}: JSON parse error: {e}"))
            parse_errors += 1

    if parse_errors:
        return violations  # can't meaningfully check structure with parse failures

    if not rows:
        violations.append(V("non_empty", "error", "track file is empty"))
        return violations

    # session_start present
    has_session_start = any(r.get("event") == "session_start" for r in rows)
    if not has_session_start:
        violations.append(V("session_start_present", "warn",
                            "no session_start entry found"))

    # Exactly one terminal closeout, as the last entry
    closeouts = [r for r in rows if r.get("event") == "closeout"]
    if not closeouts:
        violations.append(V("terminal_closeout", "warn",
                            "no closeout entry — session may be in-progress"))
    elif len(closeouts) > 1:
        violations.append(V("terminal_closeout", "error",
                            f"{len(closeouts)} closeout entries — expected exactly 1"))
    else:
        if rows[-1].get("event") != "closeout":
            violations.append(V("terminal_closeout", "error",
                                "closeout is not the last entry — entries orphaned after terminal"))

    # Entries after terminal closeout
    if rows and rows[-1].get("event") == "closeout":
        post = [r for r in rows[rows.index(rows[-1]) + 1:]]
        if post:
            violations.append(V("no_orphaned_entries", "error",
                                f"{len(post)} entries after terminal closeout"))

    # Per-turn attribution + content
    turn_entries = [r for r in rows if r.get("event") == "turn"]
    for r in turn_entries:
        turn_id = f"turn:{r.get('turn', '?')}"
        if not r.get("contributor"):
            violations.append(V("turn_attribution", "warn",
                                f"{turn_id}: missing contributor field"))
        if not r.get("kind"):
            violations.append(V("turn_attribution", "warn",
                                f"{turn_id}: missing kind field"))
        if not r.get("origin_session_id") and not r.get("session_id"):
            violations.append(V("turn_attribution", "warn",
                                f"{turn_id}: missing origin_session_id/session_id"))
        has_content = bool(
            r.get("assistant_text") or r.get("tools_used") or
            r.get("thinking") or r.get("decisions")
        )
        if not has_content:
            violations.append(V("turn_content", "warn",
                                f"{turn_id}: no content (assistant_text/tools_used/thinking/decisions)"))

    return violations


def validate_spec(path, spec):
    oid = spec.get("id") or path.name
    V = lambda dim, rule, sev, detail: {
        "object": oid, "path": str(path), "dimension": dim,
        "rule": rule, "severity": sev, "detail": detail}
    status = str(spec.get("status", "")).lower()
    if status not in ("draft", "active", "deprecated"):
        yield V("flow", "lifecycle_enum", "error", f"bad spec status: {status}")
    if path.parent.name != status and status:
        yield V("flow", "folder_matches_status", "error",
                f"in {path.parent.name}/ but status={status}")
    for f in ("subject_id", "title"):
        if not _nonempty(spec.get(f)):
            yield V("completeness", "required_field", "error", f"missing '{f}'")


def run(spoke):
    spoke = Path(spoke).resolve()
    contract = _load_json(spoke / SPEC_REL)
    if not contract:
        return [{"object": "<contract>", "path": SPEC_REL, "dimension": "behavior",
                 "rule": "contract_present", "severity": "error",
                 "detail": "canonical contract spec not found"}], 0
    lug_rules = contract.get("contract", {}).get("lug", {})
    lug_ids = _all_lug_ids(spoke)
    spec_ids = _active_spec_ids(spoke)

    violations, checked = [], 0
    lugs_root = spoke / "WAI-Spoke/lugs"
    for f in lugs_root.rglob("*.json"):
        d = _load_json(f)
        if not isinstance(d, dict):
            continue
        checked += 1
        if "/spec/" in str(f):
            violations.extend(validate_spec(f, d))
        else:
            violations.extend(validate_lug(f, d, lug_rules, spoke, lug_ids, spec_ids))
    return violations, checked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spoke-path", default=".")
    ap.add_argument("--track", metavar="PATH",
                    help="Validate a session track.jsonl file instead of lug objects")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="treat warn as failure too")
    args = ap.parse_args()

    if args.track:
        violations = validate_track(args.track)
        errors = [v for v in violations if v["severity"] == "error"]
        warns = [v for v in violations if v["severity"] == "warn"]
        if args.json:
            print(json.dumps({"track": args.track, "errors": len(errors),
                              "warnings": len(warns), "violations": violations}, indent=2))
        else:
            status = "PASS" if not errors else "FAIL"
            print(f"Track validation [{status}]: {len(errors)} error(s), {len(warns)} warning(s)")
            for v in errors + warns:
                print(f"  [{v['severity']:5}] {v['rule']:30} {v['detail']}")
        fail = errors or (warns and args.strict)
        sys.exit(1 if fail else 0)

    violations, checked = run(args.spoke_path)
    errors = [v for v in violations if v["severity"] == "error"]
    warns = [v for v in violations if v["severity"] == "warn"]

    if args.json:
        print(json.dumps({"checked": checked, "errors": len(errors),
                          "warnings": len(warns), "violations": violations}, indent=2))
    else:
        print(f"Canonical validation: {checked} objects checked, "
              f"{len(errors)} error(s), {len(warns)} warning(s)")
        for v in errors + warns:
            print(f"  [{v['severity']:5}] {v['dimension']:12} {v['rule']:24} "
                  f"{v['object']}: {v['detail']}")

    fail = errors or (warns and args.strict)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
