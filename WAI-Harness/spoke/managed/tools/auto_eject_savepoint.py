#!/usr/bin/env python3
"""Auto-eject savepoint: the EXISTENCE guarantee half of the savepoint resume
contract (impl-savepoint-loss-safety-net-v1, spec-savepoint-resume-contract-v1).

v4's validate_savepoint.py guarantees a savepoint's QUALITY once written, but
nothing guaranteed one gets written AT ALL — savepoint creation lived only inside
/wai-closeout, which a session can skip (context blowout, abandon, /clear, crash).
A session ending any other way lost 100% of its resume state. This tool is the
Stop-time safety net: when a session ends with substantive unfinished work and no
savepoint exists for it, write a DEGRADED-but-DURABLE auto-eject savepoint so the
next session resumes from disk instead of archaeology.

HARNESS-MODE-AWARE (works in both trees, one file):
  v3 working base = <root>/WAI-Spoke
  v4 working base = <root>/WAI-Harness/spoke/local
Mode selection mirrors .claude/hooks/harness_mode.sh: explicit WAI_HARNESS_MODE
override wins, else prefer v4 when present, else v3.

The auto-eject savepoint is stamped status='auto-eject' + degraded=true and carries
an honest_flag that it is machine-reconstructed and may be incomplete. It is EXEMPT
from validate_savepoint.py's full hard gate (a degraded record beats nothing), but
it is a real, on-disk, resume-path-visible savepoint.

CLI:
    python3 tools/auto_eject_savepoint.py --session <id> [--root DIR]
        [--mode v3|v4] [--dry-run]
    exit 0 always (a safety net never blocks Stop); prints a JSON status line.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wai_paths  # noqa: E402  the single source of truth for harness-mode roots


def resolve_working_base(root, mode=None):
    """Return (working_base, mode) via the canonical wai_paths resolver. Kept as a
    thin wrapper so existing callers/tests keep their signature; all mode logic now
    lives in tools/wai_paths.py (mirrors .claude/hooks/harness_mode.sh)."""
    return wai_paths.resolve_wai_root(root, mode)


def _paths(working_base):
    return {
        "savepoints": os.path.join(working_base, "savepoints"),
        "lugs": os.path.join(working_base, "lugs"),
        "sessions": os.path.join(working_base, "sessions"),
        "state": os.path.join(working_base, "WAI-State.json"),
    }


def in_progress_lugs(lugs_dir):
    """Lug ids currently in any bytype/*/in_progress/ (the lug_locks signal)."""
    out = []
    for f in sorted(glob.glob(os.path.join(lugs_dir, "bytype", "*", "in_progress", "*.json"))):
        out.append(os.path.basename(f)[:-5])
    return out


def uncommitted_work(root):
    """True if git reports any tracked/untracked change. Best-effort: a non-repo
    or git error returns [] (we do not block on git)."""
    try:
        r = subprocess.run(
            ["git", "-C", root, "status", "--porcelain"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return []
        return [ln for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def next_recommendation(state_path):
    try:
        d = json.load(open(state_path))
    except Exception:
        return ""
    rec = (d.get("_session_state", {}) or {}).get("next_session_recommendation", "")
    if isinstance(rec, str) and rec.strip() and rec.strip().lower() != "none":
        return rec.strip()
    return ""


def savepoint_exists_for_session(savepoints_dir, session_id):
    """A savepoint already covers this session if any *.json (active or completed)
    has claiming_session_id, claiming_session, session_id, or id matching it."""
    sid = session_id
    short = sid.split(".")[0]  # tolerate session-guard suffix (".contributor")
    pats = [
        os.path.join(savepoints_dir, "*.json"),
        os.path.join(savepoints_dir, "completed", "*.json"),
    ]
    for pat in pats:
        for f in glob.glob(pat):
            try:
                d = json.load(open(f))
            except Exception:
                continue
            for k in ("claiming_session_id", "claiming_session", "session_id"):
                v = str(d.get(k, ""))
                if v and (v == sid or v == short or v.split(".")[0] == short):
                    return os.path.basename(f)
    return None


def track_tail(sessions_dir, session_id, n=8):
    """Best-effort: return the last n track entries (as compact dicts) for seeding
    work_done. Tries the exact session dir, then the newest session dir."""
    short = session_id.split(".")[0]
    candidates = [os.path.join(sessions_dir, short, "track.jsonl")]
    if not os.path.exists(candidates[0]):
        dirs = sorted(glob.glob(os.path.join(sessions_dir, "*")), reverse=True)
        candidates += [os.path.join(d, "track.jsonl") for d in dirs]
    for path in candidates:
        if os.path.exists(path):
            try:
                lines = [l for l in open(path).read().splitlines() if l.strip()]
            except Exception:
                continue
            tail = []
            for l in lines[-n:]:
                try:
                    tail.append(json.loads(l))
                except Exception:
                    pass
            return tail
    return []


def detect_unfinished(working_base, root):
    """Return (is_unfinished, signals)."""
    p = _paths(working_base)
    locks = in_progress_lugs(p["lugs"])
    dirty = uncommitted_work(root)
    rec = next_recommendation(p["state"])
    signals = {
        "in_progress_lugs": locks,
        "uncommitted_files": len(dirty),
        "next_recommendation": rec,
    }
    return (bool(locks) or bool(dirty) or bool(rec)), signals


def build_autoeject(session_id, working_base, root, signals, mode):
    p = _paths(working_base)
    tail = track_tail(p["sessions"], session_id)
    work_done = []
    for t in tail:
        what = t.get("summary") or t.get("what") or t.get("action")
        if what:
            work_done.append({"what": str(what)[:300], "evidence": "track entry (auto-seeded)", "verified": False})
    if not work_done:
        work_done = [{
            "what": "Session ended without /wai-closeout; no per-turn summaries were recoverable from the track.",
            "evidence": "auto-eject from " + (p["sessions"]),
            "verified": False,
        }]
    rec = signals.get("next_recommendation") or "Run /wai and review the in_progress lugs + git status; no explicit next step was recorded."
    return {
        "id": "sp-" + session_id.split(".")[0] + "-autoeject",
        "slug": "autoeject",
        "session_id": session_id,
        "claiming_session_id": None,
        "status": "auto-eject",
        "degraded": True,
        "schema_version": 2,
        "harness_mode": mode,
        "git_sha": _git_sha(root),
        "git_branch": _git_branch(root),
        "work_done": work_done,
        "where_we_are": "AUTO-EJECT: this session ended without a savepoint or closeout. State below is machine-reconstructed from the track tail, in_progress lugs, and git status — treat as a lead, not a contract.",
        "first_actions": [{
            "order": 1,
            "action": rec,
            "command_or_target": None,
            "depends_on": None,
            "needs_authorization": None,
        }],
        "in_progress_lugs": signals.get("in_progress_lugs", []),
        "uncommitted_files": signals.get("uncommitted_files", 0),
        "honest_flags": [{
            "flag": "AUTO-GENERATED savepoint (status=auto-eject, degraded=true). It was written by the Stop-hook safety net, not authored by the session. work_done/first_actions are reconstructed and may be incomplete or wrong.",
            "why_it_matters": "A degraded-but-durable resume lead beats total loss, but do not trust it as a full resume contract — verify against git history and the in_progress lugs.",
            "where_recorded": None,
        }],
        "deferred": [],
        "pending_handoffs": [],
        "blockers_and_human_gates": [],
        "open_questions": [],
        "paper_trail": {"topics": ["auto-eject"], "decisions": []},
        "created_by": "auto_eject_savepoint.py",
    }


def _git_sha(root):
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _git_branch(root):
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def run(session_id, root, mode=None, dry_run=False):
    """Core entry. Returns a status dict (also the structure tests assert on)."""
    working_base, active = resolve_working_base(root, mode)
    if working_base is None:
        return {"action": "skip", "reason": "no harness root (neither WAI-Spoke nor WAI-Harness)", "mode": active}
    p = _paths(working_base)
    existing = savepoint_exists_for_session(p["savepoints"], session_id)
    if existing:
        return {"action": "skip", "reason": "savepoint already exists for session", "savepoint": existing, "mode": active}
    unfinished, signals = detect_unfinished(working_base, root)
    if not unfinished:
        return {"action": "skip", "reason": "no substantive unfinished work", "mode": active, "signals": signals}
    sp = build_autoeject(session_id, working_base, root, signals, active)
    dest = os.path.join(p["savepoints"], sp["id"] + ".json")
    if not dry_run:
        os.makedirs(p["savepoints"], exist_ok=True)
        json.dump(sp, open(dest, "w"), indent=2)
    return {"action": "wrote" if not dry_run else "would-write", "savepoint": dest, "mode": active, "signals": signals}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="current session id")
    ap.add_argument("--root", default=".", help="spoke root (default .)")
    ap.add_argument("--mode", choices=["v3", "v4"], default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    status = run(a.session, os.path.abspath(a.root), a.mode, a.dry_run)
    print(json.dumps(status))
    return 0  # a safety net never blocks Stop


if __name__ == "__main__":
    sys.exit(main())
