#!/usr/bin/env python3
"""verification_spine.py — the v4 Verification & Quality spine core (Stream M).

(impl-verification-spine-core-v1) Unifies the scattered verification pieces into
ONE auditable, mechanical core that threads through the lifecycle:

  q1 test-at-birth   — a lug cannot open unless every AC maps to a runnable test
                       AND the test was reviewed by a second party (a wrong AC
                       begets a wrong test; existence is not correctness).
  q2 coverage        — lug coverage %, null rate, certification_score, stale tests.
  q3 pre-user gate   — tiered bar by visibility: internal=mechanical;
                       count/aggregation=mechanical+semantic (two-pass — a count
                       of 40 of the wrong type is a semantic bug mechanical misses);
                       user-facing=+experiential AND the fresh-actor rule (the gate
                       certifying 'show user' is not the agent that produced the
                       work or its test). null is first-class but MUST be disclosed.
  q4 logging/routing — every failure routes to an owner; repeated failure escalates.

All functions are pure over injected data so the spine is itself unit-tested.
The experiential browser/Playwright gate is intentionally out of scope here (it
needs the multimodal sandbox runtime) — modeled as a required check, enforced
elsewhere, never silently skipped.
"""
import os

# the typed gap taxonomy — a gap is exposed when it appears on its surface
GAP_TYPES = {
    "test-null":            {"detector": "QA/coverage",          "surface": "Quality Health null rate"},
    "ac-uncovered":         {"detector": "lug-reviewer",         "surface": "test-at-birth gate (blocks open)"},
    "path-untested":        {"detector": "QA + GitNexus",        "surface": "Quality Health coverage %"},
    "capability-missing":   {"detector": "Aimer vs CapabilitiesGraph", "surface": "adoption gap report"},
    "decision-undocumented": {"detector": "Historian",           "surface": "survey gap list"},
    "cruft/misplacement":   {"detector": "Historian/Asset-Reviewer", "surface": "Hygiene adoption-correctness"},
    "deprecation-live":     {"detector": "self-healing AC22 + Trainer", "surface": "stale-write trend"},
}

DEFAULT_STALE_VERSIONS = 2
RETRY_CAP = 2


# ---------- q1: test-at-birth gate ----------
def test_at_birth_gate(lug):
    """A lug may go draft->open only if it has a runnable verification_test, every
    acceptance criterion is covered by a verify[] step, and the test was reviewed
    by a second party (not just the author). Returns the gate verdict."""
    acs = lug.get("acceptance_criteria") or []
    verify = lug.get("verify") or []
    has_test = bool(lug.get("verification_test"))
    reviewed = bool(lug.get("reviewed_by"))
    # AC<->test traceability: each AC needs at least one verify step (mechanical heuristic)
    uncovered = []
    if len(verify) < len(acs):
        # the last (len(acs)-len(verify)) ACs are considered uncovered
        uncovered = acs[len(verify):]
    ok = has_test and reviewed and not uncovered and bool(verify)
    reasons = []
    if not has_test:
        reasons.append("no runnable verification_test")
    if not verify:
        reasons.append("empty verify[] (no test spec)")
    if uncovered:
        reasons.append(f"{len(uncovered)} acceptance criteria uncovered by verify[]")
    if not reviewed:
        reasons.append("test not reviewed by a second party (test-quality gate)")
    return {"ok": ok, "has_test": has_test, "reviewed": reviewed,
            "uncovered_acs": uncovered,
            "gap": None if ok else "ac-uncovered" if uncovered else "test-null",
            "reasons": reasons}


# ---------- q2: coverage maintenance ----------
def compute_coverage(lugs, test_results, current_version=None, stale_window=DEFAULT_STALE_VERSIONS):
    """Coverage honesty: lug coverage %, null rate, certification_score, stale[].
    test_results rows: {test_id, owner_id, result: pass|fail|null, version}."""
    total_lugs = len(lugs) or 1
    covered = sum(1 for l in lugs if l.get("verification_test"))
    lug_coverage_pct = round(covered / total_lugs, 3)

    passes = sum(1 for r in test_results if r.get("result") == "pass")
    fails = sum(1 for r in test_results if r.get("result") == "fail")
    nulls = sum(1 for r in test_results if r.get("result") == "null")
    total_checks = passes + fails + nulls or 1
    null_rate = round(nulls / total_checks, 3)
    certification_score = round(passes / total_checks, 3)

    # stale: a test whose last run is more than stale_window versions behind current
    stale = []
    if current_version is not None:
        for r in test_results:
            v = r.get("version")
            try:
                if v is not None and (current_version - int(v)) > stale_window:
                    stale.append(r.get("test_id"))
            except (TypeError, ValueError):
                continue
    return {"lug_coverage_pct": lug_coverage_pct, "null_rate": null_rate,
            "certification_score": certification_score, "stale": stale,
            "passes": passes, "fails": fails, "nulls": nulls}


# ---------- q3: tiered pre-user quality gate ----------
def tier_for(visibility):
    """Map a visibility class to the quality tier it must clear."""
    if visibility in ("user-facing", "user_facing"):
        return "user_facing"
    if visibility in ("count", "aggregation", "summary"):
        return "count"
    return "mechanical"


def _check_result(checks, mode):
    """Result of the named check mode: 1, 0, 'null', or None if absent."""
    for c in checks:
        if c.get("mode") == mode:
            return c.get("result")
    return None


def pre_user_gate(visibility, checks, producer=None, gate_actor=None):
    """Gate the 'show user' step. Returns whether the work may be surfaced, the
    reason, and any disclosed null gaps. The bar scales with visibility; the
    fresh-actor rule applies at the user-facing boundary."""
    tier = tier_for(visibility)
    disclosed_nulls = [c.get("check") for c in checks if c.get("result") == "null"]

    def blocked(reason):
        return {"show_user": False, "tier": tier, "reason": reason,
                "disclosed_nulls": disclosed_nulls}

    if _check_result(checks, "mechanical") != 1:
        return blocked("mechanical bar not met (code must run / assertions green)")
    if tier in ("count", "user_facing") and _check_result(checks, "semantic") != 1:
        return blocked("semantic bar not met — two-pass required (inspect actual items, "
                       "not just keys present)")
    if tier == "user_facing":
        if _check_result(checks, "experiential") != 1:
            return blocked("experiential bar not met — must be verified in the target "
                           "medium (rendered/run), not well-formed on disk")
        if gate_actor is None or producer is None or gate_actor == producer:
            return blocked("fresh-actor rule: the gate certifying 'show user' must not be "
                           "the agent that produced the work or its test")
    # passing — but any null gap must be disclosed alongside the work
    return {"show_user": True, "tier": tier,
            "reason": "tier bar met" + (" (with disclosed gaps)" if disclosed_nulls else ""),
            "disclosed_nulls": disclosed_nulls}


# ---------- q4: Quality Health + failure routing ----------
def quality_health(coverage, failing_suites=None):
    """The wakeup 'Quality Health' section."""
    failing_suites = failing_suites or []
    return {"coverage_pct": coverage.get("lug_coverage_pct"),
            "null_rate": coverage.get("null_rate"),
            "certification_score": coverage.get("certification_score"),
            "stale_count": len(coverage.get("stale", [])),
            "failing_suites": failing_suites}


def route_failure(test_result, prior_failures=0, cap=RETRY_CAP):
    """No silent failures: a failing test routes to its owning advisor; repeated
    failure past the cap escalates to a Historian signal."""
    if test_result.get("result") != "fail":
        return {"routed": False}
    owner_type = test_result.get("owner_type", "lug")
    owner = {"flow": "qa", "advisor": "qa", "lug": test_result.get("owner_id")}.get(owner_type, "qa")
    escalate = (prior_failures + 1) > cap
    return {"routed": True, "owner": owner,
            "escalate": escalate,
            "signal": "historian" if escalate else None,
            "gap": "test-null" if test_result.get("result") == "null" else None}


# ---------- q1b: completion gate (AC-linkage mandatory at open->completed) ----------
def _ac_token(s):
    import re
    m = re.search(r"AC\d+", str(s or ""), re.IGNORECASE)
    return m.group(0).upper() if m else ""


def completion_gate(lug):
    """A lug with a parent_epic may go open/in_progress -> completed ONLY if it records
    the AC evidence linkage the epic derives status from. This closes the root cause of
    the S45 AC-drift episode: 23 lugs completed with NO closes_epic_acs, so the epic
    over-reported 20 ACs as done with zero evidence.

    Requires:
      - closes_epic_acs present and non-empty, AND
      - every coverage:full entry carries a verification_test whose covers_ac names THAT
        epic AC with result==1 (else it must be coverage:partial). Prevents a bare 'full'
        claim with no proving test (the false-promote the reconciler guards against).

    Lugs with NO parent_epic are EXEMPT (ok=True) — not all work closes an epic AC.
    Callers block the completion move on ok==False.
    """
    parent = lug.get("parent_epic") or lug.get("epic")
    if not parent:
        return {"ok": True, "exempt": True, "reasons": []}
    # Explicit escape: supporting work under an epic that closes NO specific AC must
    # SAY SO (closes_no_ac: "<reason>") — a conscious acknowledgment, not a silent skip.
    if lug.get("closes_no_ac"):
        return {"ok": True, "exempt": True, "reasons": [],
                "note": "closes_no_ac: " + str(lug.get("closes_no_ac"))[:120]}
    closes = lug.get("closes_epic_acs") or []
    reasons = []
    if not closes:
        return {"ok": False, "exempt": False, "gap": "ac-unlinked",
                "reasons": ["parent_epic lug has no closes_epic_acs and no closes_no_ac "
                            "acknowledgment (AC linkage is mandatory at completion; "
                            "set closes_no_ac:'<reason>' if it genuinely closes no AC)"]}
    vts = lug.get("verification_test") or []
    for entry in closes:
        if isinstance(entry, str):
            ac, cov = entry, "full"
        elif isinstance(entry, dict):
            ac, cov = entry.get("ac", ""), entry.get("coverage", "full")
        else:
            reasons.append(f"malformed closes_epic_acs entry: {entry!r}")
            continue
        ac_id = _ac_token(ac)
        if not ac_id:
            reasons.append(f"closes_epic_acs entry names no AC: {entry!r}")
            continue
        if cov == "full":
            green = any(
                isinstance(t, dict)
                and _ac_token(t.get("covers_ac", "")) == ac_id
                and t.get("result") == 1
                for t in vts
            )
            if not green:
                reasons.append(
                    f"{ac_id}: coverage:full needs a verification_test with "
                    f"covers_ac={ac_id} result==1, or downgrade to coverage:partial")
    ok = not reasons
    return {"ok": ok, "exempt": False, "gap": None if ok else "ac-unlinked",
            "reasons": reasons}


if __name__ == "__main__":
    print("verification_spine: q1 test-at-birth, q1b completion gate, q2 coverage, q3 pre-user gate, q4 routing")
    print("gap taxonomy:", ", ".join(GAP_TYPES))
