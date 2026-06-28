#!/usr/bin/env python3
"""observability_dashboard.py - oversight surfaces (spec-observability-oversight-v1).

The read-only SURFACE layer of the observability spine: it answers the spec's
three-question confidence model - "what is happening / is it on track / what needs
me" - each backed by a live surface with a FRESHNESS contract, computed over the
event/stream sources that already exist on disk (lug queue dirs, advisor
lifecycle.jsonl, advisor scan_state.json, the current session track, and the
harness.db query tables). It never mutates anything it reads.

Why a surface layer over the existing streams (not an emitter migration first):
the events table is empty today, but the data the user needs IS on disk - it is
just scattered and carries no freshness signal, so a silently-stale surface reads
as current. This module unifies those sources into three surfaces and makes
staleness itself OBSERVABLE: a source older than its surface's cadence (or absent
entirely) is badged STALE with its age, never presented as current. Emitter
migration, correlation-chain queries (explain_chain.py), workflow-object live
status, and trend curves are deferred follow-ons (see the lug's deferred_followups).

Pure core: build_dashboard(spoke_path, now_ts) -> dict. The CLI wraps it with IO
(--json writes WAI-Spoke/runtime/observability-dashboard.json; --render prints
human text). now_ts is injected so tests are deterministic.
"""
import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LUG_TYPES = ("implementation", "task", "epic", "bug", "feature", "spec")
QUEUE_STATUSES = ("open", "in_progress")

# freshness cadences in seconds (spec freshness_contracts.examples)
CADENCE = {"now": 300, "attention": 300, "on_track": 86400}

# attention queue depth past which the queue is itself a P1 "attention overloaded"
# alarm (spec attention_surface: max-depth alarm)
ATTENTION_MAX_DEPTH = 25

# how far back the attention surface looks (it answers "what needs me NOW"); also
# bounds the 423-deep lifecycle rollback history so it cannot flood the surface
ATTENTION_WINDOW_SECONDS = 24 * 3600

# severity weights feeding priority = severity * (1 + age_days)
SEVERITY = {"escalation": 5, "rollback": 4, "stalled": 3, "sign_off": 3, "needs_you": 2}

# the "what needs ME" lens: every attention item is classified human (only the user
# can resolve it — a gate, sign-off, decision, escalation, cross-spoke coordination)
# vs automatable (an agent can run it — a stalled lug with a model fit, a self-heal
# rollback). The human bucket IS "what needs me"; the automatable bucket is pipeline
# visibility, not the user's to-do.
_HUMAN_SIGNALS = ("human", "mario", "cutover", "teardown", "sign-off", "sign off",
                  "signoff", "activation", "activate", "decision", "approve",
                  "your call", "human_gate", "needs_human")


def classify_disposition(severity_key, reason="", lug=None):
    """Return 'human' or 'automatable' for an attention item."""
    text = str(reason or "").lower()
    if severity_key in ("sign_off", "escalation", "needs_you"):
        return "human"
    if severity_key == "rollback":
        return "automatable"            # auto-rollback is the system self-healing
    if lug is not None:
        if lug.get("human_gate") or lug.get("needs_human"):
            return "human"
        bb = " ".join(str(x) for x in (lug.get("blocked_by") or []))
        if any(k in bb.lower() for k in _HUMAN_SIGNALS):
            return "human"
        if lug.get("model_fit") and lug.get("execution_mode"):
            return "automatable"        # carries a model fit + run mode -> agent can do it
    if any(k in text for k in _HUMAN_SIGNALS):
        return "human"
    return "automatable"

# lifecycle event_types that warrant the user's attention, mapped to a severity key
LIFECYCLE_ATTENTION = {
    "auto_rolled_back": "rollback",
    "rolled_back": "rollback",
    "escalated": "escalation",
    "escalation": "escalation",
    "degraded": "rollback",
}


def _spoke(spoke_path):
    """Resolve the spoke WORKING BASE, base-aware. On a v4 spoke this routes to
    WAI-Harness/spoke/local instead of the nonexistent WAI-Spoke tree, so the
    surfaces read live lugs/sessions/savepoints (impl-fix-p2-v3noop-sweep-v1)."""
    p = Path(spoke_path)
    if p.name in ("WAI-Spoke", "local"):
        return p
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import wai_paths
        root, mode = wai_paths.resolve_wai_root(str(p))
        if root and mode != "none":
            return Path(root)
    except Exception:
        pass
    return p / "WAI-Spoke"  # last-resort v3 fallback


def _advisors_root(spoke):
    """Advisors are the one category NOT under the working base. In v4 they live at
    WAI-Harness/spoke/advisors (sibling of local); in v3 at WAI-Spoke/advisors."""
    if spoke.name == "local" and spoke.parent.name == "spoke":
        return spoke.parent / "advisors"
    return spoke / "advisors"


def _managed_root(spoke):
    """managed/ (harness.db) is a sibling of the working base in v4
    (WAI-Harness/spoke/managed); under WAI-Spoke in v3."""
    if spoke.name == "local" and spoke.parent.name == "spoke":
        return spoke.parent / "managed"
    return spoke / "managed"


def _parse_ts(s):
    """ISO-8601 string -> epoch seconds (float), or None if unparseable."""
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


def _now_epoch(now_ts):
    """now_ts may be an epoch float/int, an ISO string, or None (-> wall clock)."""
    if now_ts is None:
        return datetime.now(timezone.utc).timestamp()
    if isinstance(now_ts, (int, float)):
        return float(now_ts)
    parsed = _parse_ts(str(now_ts))
    return parsed if parsed is not None else datetime.now(timezone.utc).timestamp()


def _fmt_age(seconds):
    if seconds is None:
        return "no data"
    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m"
    return f"{seconds}s"


def _newest_mtime(paths):
    newest = None
    for p in paths:
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        if newest is None or mt > newest:
            newest = mt
    return newest


def freshness(source_ts, cadence_seconds, now_epoch):
    """A surface is fresh if its newest source is within cadence. No source data
    at all -> STALE (no data): emptiness is made visible, never silently 'current'.
    """
    if source_ts is None:
        return {"fresh": False, "age_seconds": None, "cadence_seconds": cadence_seconds,
                "badge": "STALE (no data)"}
    age = max(0.0, now_epoch - source_ts)
    fresh = age <= cadence_seconds
    return {
        "fresh": fresh,
        "age_seconds": age,
        "cadence_seconds": cadence_seconds,
        "badge": None if fresh else f"STALE ({_fmt_age(age)})",
    }


# --- now surface ------------------------------------------------------------

def build_now_surface(spoke, now_epoch):
    queue_depth = {}
    lug_files = []
    total = 0
    for t in LUG_TYPES:
        for s in QUEUE_STATUSES:
            fs = glob.glob(str(spoke / "lugs" / "bytype" / t / s / "*.json"))
            if fs:
                queue_depth.setdefault(t, {})[s] = len(fs)
                total += len(fs)
                lug_files.extend(fs)

    advisors = []
    advisor_states = glob.glob(str(_advisors_root(spoke) / "*" / "scan_state.json"))
    for f in sorted(advisor_states):
        try:
            d = json.loads(Path(f).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        advisors.append({
            "id": d.get("advisor_id") or Path(f).parent.name,
            "status": d.get("status"),
            "activation": d.get("activation"),
        })

    # recent activity from the most-recent session track
    recent_1h = recent_24h = 0
    track_ts = None
    tracks = glob.glob(str(spoke / "sessions" / "*" / "track.jsonl"))
    track = max(tracks, key=lambda p: os.path.getmtime(p)) if tracks else None
    if track:
        try:
            for line in Path(track).read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ets = _parse_ts(entry.get("ts") or entry.get("user_ts"))
                if ets is None:
                    continue
                if track_ts is None or ets > track_ts:
                    track_ts = ets
                age = now_epoch - ets
                if age <= 3600:
                    recent_1h += 1
                if age <= 86400:
                    recent_24h += 1
        except OSError:
            pass

    source_ts_candidates = [t for t in (_newest_mtime(lug_files),
                                        _newest_mtime(advisor_states),
                                        track_ts) if t is not None]
    source_ts = max(source_ts_candidates) if source_ts_candidates else None

    return {
        "queue_depth": queue_depth,
        "queue_total": total,
        "advisors": advisors,
        "advisor_count": len(advisors),
        "recent_activity": {"last_1h": recent_1h, "last_24h": recent_24h},
        "_source_ts": source_ts,
    }


# --- attention surface ------------------------------------------------------

def _attention_item(source, subject_ref, severity_key, reason, item_ts, now_epoch, lug=None):
    severity = SEVERITY.get(severity_key, 1)
    age = max(0.0, now_epoch - item_ts) if item_ts is not None else 0.0
    age_days = age / 86400.0
    return {
        "source": source,
        "subject_ref": subject_ref,
        "severity_key": severity_key,
        "severity": severity,
        "reason": reason,
        "age_seconds": age,
        "priority": round(severity * (1 + age_days), 4),
        "disposition": classify_disposition(severity_key, reason, lug),
        "_ts": item_ts,
    }


def build_attention_surface(spoke, now_epoch):
    items = []
    source_ts = None

    # (a) advisor lifecycle: rollbacks / escalations / degradations, windowed to
    # the last 24h and deduped to the most-recent event per (advisor, type) so the
    # 400+-deep rollback history cannot flood "what needs me now".
    lifecycle = _advisors_root(spoke) / "lifecycle.jsonl"
    if lifecycle.exists():
        latest = {}
        try:
            for line in lifecycle.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                et = e.get("event_type")
                sev = LIFECYCLE_ATTENTION.get(et)
                if not sev:
                    continue
                ts = _parse_ts(e.get("ts"))
                if ts is None:
                    continue
                if source_ts is None or ts > source_ts:
                    source_ts = ts
                if now_epoch - ts > ATTENTION_WINDOW_SECONDS:
                    continue
                key = (e.get("advisor_id"), et)
                if key not in latest or ts > latest[key][0]:
                    latest[key] = (ts, e, sev)
        except OSError:
            pass
        for (advisor_id, et), (ts, e, sev) in latest.items():
            reason = e.get("reason") or et
            items.append(_attention_item(
                "lifecycle", advisor_id, sev,
                f"{et}: {reason}", ts, now_epoch))

    # (b) stalled lugs: autopilot_failures >= 2 OR needs_attention truthy
    for t in LUG_TYPES:
        for s in QUEUE_STATUSES:
            for f in glob.glob(str(spoke / "lugs" / "bytype" / t / s / "*.json")):
                try:
                    lug = json.loads(Path(f).read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                failures = lug.get("autopilot_failures") or 0
                stalled = (isinstance(failures, int) and failures >= 2) or bool(lug.get("needs_attention"))
                if not stalled:
                    continue
                ts = _parse_ts(lug.get("updated_at") or lug.get("created_at"))
                if ts is not None and (source_ts is None or ts > source_ts):
                    source_ts = ts
                reason = (lug.get("needs_attention") if isinstance(lug.get("needs_attention"), str)
                          else f"autopilot stalled ({failures} failures)")
                items.append(_attention_item(
                    "lug", lug.get("id") or Path(f).stem, "stalled", reason, ts, now_epoch, lug=lug))

    # (c) human-gate / sign-off items: active|pending savepoints with an unresolved
    # human gate, and any open lug flagged human_gate truthy
    for f in glob.glob(str(spoke / "savepoints" / "*.json")):
        try:
            sp = json.loads(Path(f).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if sp.get("status") not in ("active", "pending"):
            continue
        gates = sp.get("blockers_and_human_gates") or []
        for g in gates:
            owner = str(g.get("owner", "")).lower()
            if "human" in owner or "mario" in owner:
                ts = _parse_ts(sp.get("claimed_at") or sp.get("created_at"))
                if ts is not None and (source_ts is None or ts > source_ts):
                    source_ts = ts
                items.append(_attention_item(
                    "savepoint", sp.get("id") or Path(f).stem, "sign_off",
                    g.get("gate") or "human sign-off required", ts, now_epoch))

    # (d) human-action work: open/in_progress + incoming lugs explicitly flagged
    # human (human_gate / needs_human / blocked-by-human/cutover/activation). These
    # are work ONLY the user can resolve — they belong on "what needs me", not the
    # automatable pipeline. Targeted (flagged-only) so it cannot flood.
    seen_human = set()
    human_globs = [str(spoke / "lugs" / "bytype" / t / s / "*.json")
                   for t in LUG_TYPES for s in QUEUE_STATUSES]
    human_globs.append(str(spoke / "lugs" / "incoming" / "*.json"))
    for g in human_globs:
        for f in glob.glob(g):
            try:
                lug = json.loads(Path(f).read_text())
            except (OSError, json.JSONDecodeError):
                continue
            lid = lug.get("id") or Path(f).stem
            if lid in seen_human:
                continue
            bb = " ".join(str(x) for x in (lug.get("blocked_by") or []))
            human = (lug.get("human_gate") or lug.get("needs_human")
                     or any(k in bb.lower() for k in _HUMAN_SIGNALS))
            if not human:
                continue
            seen_human.add(lid)
            ts = _parse_ts(lug.get("updated_at") or lug.get("created_at"))
            if ts is not None and (source_ts is None or ts > source_ts):
                source_ts = ts
            items.append(_attention_item(
                "lug", lid, "needs_you",
                f"human action: {lug.get('title') or lid}", ts, now_epoch, lug=lug))

    items.sort(key=lambda i: i["priority"], reverse=True)
    needs_you = [i for i in items if i["disposition"] == "human"]
    automatable = [i for i in items if i["disposition"] == "automatable"]
    return {
        "items": items,
        "count": len(items),
        "needs_you": needs_you,           # the "what needs ME" bucket (human-only)
        "automatable": automatable,       # pipeline visibility, not the user's to-do
        "needs_you_count": len(needs_you),
        "automatable_count": len(automatable),
        "overloaded": len(needs_you) > ATTENTION_MAX_DEPTH,
        "max_depth": ATTENTION_MAX_DEPTH,
        "_source_ts": source_ts,
    }


# --- on-track surface -------------------------------------------------------

def build_on_track_surface(spoke, now_epoch):
    """Trajectory: certification / quality from harness.db test_results (+ recent
    completions). The test tables are empty today, so this surface will read STALE
    - that is the honest signal, not a hidden gap."""
    tests = {"pass": 0, "fail": 0, "null": 0, "total": 0}
    source_ts = None
    db = _managed_root(spoke) / "harness.db"
    if db.exists():
        try:
            import sqlite3
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            try:
                cur = con.execute("SELECT result, COUNT(*) FROM test_results GROUP BY result")
                for result, n in cur.fetchall():
                    tests["total"] += n
                    if result in (1, "1", "pass"):
                        tests["pass"] += n
                    elif result in (0, "0", "fail"):
                        tests["fail"] += n
                    else:
                        tests["null"] += n
                row = con.execute("SELECT MAX(ts) FROM test_results").fetchone()
                if row and row[0]:
                    source_ts = _parse_ts(row[0])
            finally:
                con.close()
        except Exception:
            pass

    completed_7d = 0
    comp_files = glob.glob(str(spoke / "lugs" / "bytype" / "*" / "completed" / "*.json"))
    for f in comp_files:
        try:
            lug = json.loads(Path(f).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        ts = _parse_ts(lug.get("completed_at"))
        if ts is None:
            continue
        if source_ts is None or ts > source_ts:
            source_ts = ts
        if now_epoch - ts <= 7 * 86400:
            completed_7d += 1

    pass_rate = round(tests["pass"] / tests["total"], 4) if tests["total"] else None
    return {
        "certification": {"test_results": tests, "pass_rate": pass_rate},
        "completed_last_7d": completed_7d,
        "_source_ts": source_ts,
    }


# --- assembly ---------------------------------------------------------------

def build_dashboard(spoke_path=".", now_ts=None):
    spoke = _spoke(spoke_path)
    now_epoch = _now_epoch(now_ts)

    now_s = build_now_surface(spoke, now_epoch)
    attention = build_attention_surface(spoke, now_epoch)
    on_track = build_on_track_surface(spoke, now_epoch)

    # `now` and `attention` are recomputed LIVE on every access (a direct read of
    # the current queue / advisor / lifecycle state), so their freshness contract -
    # "refreshed within cadence" - is satisfied by construction: source_ts is the
    # generation instant. (newest_source_age on `now` is exposed separately as a
    # CONTENT signal, not a freshness one - an idle-but-current surface is fresh.)
    # `on_track` is backed by the periodically-written certification artifact
    # (test_results / recent completions); it goes STALE when that artifact is old
    # or absent, which is the honest "trajectory unknown" signal.
    now_s["newest_source_age_seconds"] = (
        None if now_s["_source_ts"] is None else max(0.0, now_epoch - now_s["_source_ts"]))
    now_s["freshness"] = freshness(now_epoch, CADENCE["now"], now_epoch)
    attention["freshness"] = freshness(now_epoch, CADENCE["attention"], now_epoch)
    on_track["freshness"] = freshness(on_track["_source_ts"], CADENCE["on_track"], now_epoch)

    # the three-question confidence model: each question is answerable iff its
    # surface is present AND fresh (spec confidence_model.assertion)
    questions = {
        "what_is_happening": {"surface": "now", "answerable": now_s["freshness"]["fresh"]},
        "is_it_on_track": {"surface": "on_track", "answerable": on_track["freshness"]["fresh"]},
        "what_needs_me": {"surface": "attention", "bucket": "needs_you",
                          "answerable": attention["freshness"]["fresh"]},
    }
    defects = [name for name, q in questions.items() if not q["answerable"]]

    return {
        "generated_at": datetime.fromtimestamp(now_epoch, timezone.utc).isoformat(),
        "spoke_path": str(spoke),
        "surfaces": {"now": now_s, "on_track": on_track, "attention": attention},
        "confidence": questions,
        "observability_defects": defects,
        "attention_overloaded": attention["overloaded"],
    }


def _emit_generation_event(spoke_path, dashboard):
    """Best-effort: honor 'silent operation is banned' by emitting one typed event
    for the dashboard run. Wrapped so a missing/locked DB never breaks the surface."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import event_bus
        event_bus.emit({
            "ts": dashboard["generated_at"],
            "actor": "observability-dashboard",
            "type": "advisor_run",
            "subject_ref": "observability-dashboard",
            "status": "completed",
            "evidence": json.dumps({
                "queue_total": dashboard["surfaces"]["now"]["queue_total"],
                "attention": dashboard["surfaces"]["attention"]["count"],
                "defects": dashboard["observability_defects"],
            }),
        })
    except Exception:
        pass


def render(dashboard):
    lines = []
    lines.append("=" * 60)
    lines.append(f"OBSERVABILITY DASHBOARD  (generated {dashboard['generated_at']})")
    lines.append("=" * 60)

    def badge(surface):
        b = surface.get("freshness", {}).get("badge")
        return f"  [{b}]" if b else ""

    now_s = dashboard["surfaces"]["now"]
    lines.append(f"\nWHAT IS HAPPENING (now){badge(now_s)}")
    qd = ", ".join(f"{t}={sum(v.values())}" for t, v in now_s["queue_depth"].items()) or "(no queue)"
    lines.append(f"  queue: {now_s['queue_total']} open  ({qd})")
    lines.append(f"  advisors: {now_s['advisor_count']}  | activity 1h={now_s['recent_activity']['last_1h']} 24h={now_s['recent_activity']['last_24h']}")

    ot = dashboard["surfaces"]["on_track"]
    lines.append(f"\nIS IT ON TRACK (trajectory){badge(ot)}")
    cert = ot["certification"]
    lines.append(f"  test pass_rate: {cert['pass_rate']}  (results={cert['test_results']['total']})  | completed_7d: {ot['completed_last_7d']}")

    att = dashboard["surfaces"]["attention"]
    overload = "  *** OVERLOADED (P1) ***" if att["overloaded"] else ""
    lines.append(f"\nWHAT NEEDS ME — human-only ({att['needs_you_count']}){badge(att)}{overload}")
    for it in att["needs_you"][:10]:
        lines.append(f"  [{it['priority']:>6}] {it['source']}/{it['subject_ref']}: {it['reason']}")
    if not att["needs_you"]:
        lines.append("  (nothing requires you right now)")
    lines.append(f"\nPIPELINE — automatable ({att['automatable_count']}, agent-handled, not your to-do)")
    for it in att["automatable"][:5]:
        lines.append(f"  [{it['priority']:>6}] {it['source']}/{it['subject_ref']}: {it['reason']}")

    if dashboard["observability_defects"]:
        lines.append(f"\nOBSERVABILITY DEFECTS (unanswerable from a fresh surface): {', '.join(dashboard['observability_defects'])}")
    lines.append("")
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description="Render the observability oversight dashboard.")
    ap.add_argument("--spoke-path", default=".")
    ap.add_argument("--json", action="store_true", help="write JSON to WAI-Spoke/runtime/observability-dashboard.json")
    ap.add_argument("--render", action="store_true", help="print the human dashboard (default)")
    ap.add_argument("--no-emit", action="store_true", help="skip the best-effort event emission")
    args = ap.parse_args(argv)

    dashboard = build_dashboard(args.spoke_path)
    if not args.no_emit:
        _emit_generation_event(args.spoke_path, dashboard)

    if args.json:
        out = _spoke(args.spoke_path) / "runtime" / "observability-dashboard.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(dashboard, indent=2) + "\n")
        print(f"wrote {out}")
    if args.render or not args.json:
        print(render(dashboard))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
