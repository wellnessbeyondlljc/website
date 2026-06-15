#!/usr/bin/env python3
"""Structural validator for the v4 lug schema (spec-lug-schema-v4-v1).

This is the STRUCTURAL half of the dual promotion gate; the CONTENT half (the
cold-reader / completeness gate) is spec-object-quality-v4-v1, enforced by the
lug-reviewer. Both must pass for draft->open.

It documents an EXISTING code assumption: tools/change_registry.py check_rev()
(live since S44) already reads `rev` off lugs and rejects stale-rev writes. This
validator guarantees rev is present + integer so that guard is meaningful (an
absent rev makes check_rev return ok:False, which a careless writer treats as a
soft warning) — closing the gap where a lug could silently defeat optimistic
concurrency by simply omitting rev.

Branching on schema_version:
  - schema_version == 4  -> the full v4 structural gate (below)
  - schema_version  < 4 or absent -> {ok: True, migrate_prompt: True}
    (a migration PROMPT, never a hard reject — spec resolution)

CLI:
    python3 tools/validate_lug_v4.py <lug.json>
    exit 0 = valid (or v3 migrate-prompt); exit 1 = v4 structural failures.
"""
import json
import sys

_VALID_MODES = {"mechanical", "attested", "human", "attested_experiential"}
_VALID_RESULTS = {1, 0, None}
# Context fields required on every v4 lug; the rationale pair is required only
# when impact is high enough to warrant a recorded decision.
_ALWAYS_CONTEXT = ("situation", "context_snapshot", "triggering_session")
_HIGH_IMPACT_CONTEXT = ("decision_rationale", "alternatives_considered")
_HIGH_IMPACT_THRESHOLD = 6


def _nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def _ac_key(ac):
    """An acceptance criterion may be a string ('AC1 ...') or a dict {id/text}.
    Return a short key used to match a verification_test.covers_ac reference."""
    if isinstance(ac, dict):
        return (ac.get("id") or ac.get("text") or "").strip()
    s = str(ac).strip()
    # leading token like 'AC1' / 'AC10' is the matchable id
    tok = s.split(None, 1)[0] if s else ""
    return tok if tok.upper().startswith("AC") else s


def validate_lug_v4(lug, spoke_root="."):
    """Validate a lug dict against the v4 structural schema.

    Returns {"ok": bool, "failures": [str,...], "migrate_prompt": bool}.
    """
    sv = lug.get("schema_version")
    if not isinstance(sv, int) or sv < 4:
        return {
            "ok": True,
            "failures": [],
            "migrate_prompt": True,
            "note": f"schema_version={sv!r} (<4 or absent) — v3 lug; run v4 migration "
                    "(stamp schema_version=4 + rev=1, materialize verify[]->verification_test). "
                    "Not a hard reject.",
        }

    failures = []

    # --- rev: the optimistic-concurrency field change_registry.check_rev reads ---
    rev = lug.get("rev")
    if rev is None:
        failures.append(
            "rev required on a v4 lug (concurrency guard) — an absent rev silently "
            "defeats change_registry.check_rev (last-write-wins banned)"
        )
    elif not isinstance(rev, int) or isinstance(rev, bool):
        failures.append(f"rev must be an integer, got {type(rev).__name__} ({rev!r})")
    elif rev < 1:
        failures.append(f"rev must be >= 1 (initialized to 1 at creation), got {rev}")

    # --- mandatory context fields ---
    for f in _ALWAYS_CONTEXT:
        if not lug.get(f):
            failures.append(f"mandatory v4 context field missing/empty: {f}")
    if not _nonempty_str(lug.get("situation")):
        # situation must be a real observable condition string
        if "situation" in lug and not lug.get("situation"):
            pass  # already flagged above
    impact = lug.get("impact")
    if isinstance(impact, int) and impact >= _HIGH_IMPACT_THRESHOLD:
        for f in _HIGH_IMPACT_CONTEXT:
            v = lug.get(f)
            empty = (v is None or v == "" or v == [] or v == {})
            if empty:
                failures.append(
                    f"{f} required on impact>={_HIGH_IMPACT_THRESHOLD} lug "
                    f"(impact={impact}) — capture the decision at authoring time"
                )

    # --- verification_test: non-empty + AC traceability ---
    vt = lug.get("verification_test")
    if not isinstance(vt, list) or len(vt) == 0:
        failures.append(
            "verification_test empty — test-at-birth requires >=1 runnable test "
            "per acceptance criterion before draft->open"
        )
        vt = []
    covered = set()
    for i, t in enumerate(vt):
        if not isinstance(t, dict):
            failures.append(f"verification_test[{i}] is not an object")
            continue
        if t.get("mode") not in _VALID_MODES:
            failures.append(
                f"verification_test[{i}].mode {t.get('mode')!r} not in {sorted(_VALID_MODES)}"
            )
        if t.get("result") not in _VALID_RESULTS:
            failures.append(
                f"verification_test[{i}].result {t.get('result')!r} not in {{1,0,null}}"
            )
        ca = t.get("covers_ac")
        if ca:
            # match by the leading AC token so 'AC1: ...' covers acceptance 'AC1 ...'
            covered.add(str(ca).split(None, 1)[0].rstrip(":") if str(ca).strip() else "")
            covered.add(str(ca).strip())

    acs = lug.get("acceptance_criteria") or []
    for ac in acs:
        key = _ac_key(ac)
        if not key:
            continue
        hit = key in covered or any(key == c or key == c.rstrip(":") for c in covered)
        if not hit:
            failures.append(
                f"acceptance criterion '{key}' has no covering verification_test "
                "(AC<->test traceability, AC27)"
            )

    # --- bolt/check refs: null or non-empty string ---
    for ref in ("bolt_ref",):
        v = lug.get(ref, None)
        if v is not None and not _nonempty_str(v):
            failures.append(f"{ref} must be null or a non-empty string, got {v!r}")
    for i, t in enumerate(vt):
        if isinstance(t, dict):
            cr = t.get("check_ref", None)
            if cr is not None and not _nonempty_str(cr):
                failures.append(
                    f"verification_test[{i}].check_ref must be null or a non-empty string"
                )

    return {"ok": not failures, "failures": failures, "migrate_prompt": False}


def main(argv):
    if not argv:
        print("usage: validate_lug_v4.py <lug.json>", file=sys.stderr)
        return 2
    lug = json.load(open(argv[0]))
    r = validate_lug_v4(lug)
    if r.get("migrate_prompt"):
        print(f"MIGRATE — {r.get('note', 'v3 lug; run v4 migration')}")
        return 0
    if r["ok"]:
        print(f"OK — valid v4 lug: {argv[0]}")
        return 0
    print(f"FAIL — v4 schema NOT satisfied ({len(r['failures'])} issue(s)):")
    for f in r["failures"]:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
