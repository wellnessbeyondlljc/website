#!/usr/bin/env python3
"""Shared lug utilities — path resolution, blocking, execute-when evaluation.

Used by score_backlog.py, wai_ozi.py, and wai-chain.sh (via inline Python).
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

SPOKE = Path(os.environ["WAI_SPOKE_PATH"]) if os.environ.get("WAI_SPOKE_PATH") else Path(__file__).parent.parent / "WAI-Spoke"
BYTYPE = SPOKE / "lugs" / "bytype"


# ---------------------------------------------------------------------------
# Attribution — canonical "who / when / where in one string"
# (teaching: track-capture-transcript-safety-net-v1; impl-concurrent-session-identity-fleet-v1)
# Format: session-{YYYYMMDD-HHMM}-{cc_uuid8}.{contributor}  + kind in {user, agent}
#   when/where = the session id + Claude Code session uuid
#   who        = git user.name (human) OR the agent label (autonomous)
# Use resolve_attribution() ANYWHERE an authored_by / contributor is stamped.
# ---------------------------------------------------------------------------

def _cc_uuid8() -> str:
    u = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    return u.replace("-", "")[:8] if u else ""


def _git_user() -> str | None:
    try:
        out = subprocess.run(
            ["git", "config", "user.name"], capture_output=True, text=True, timeout=3
        ).stdout.strip()
        return out or None
    except Exception:
        return None


def resolve_worktree_origin(spoke_path: str | os.PathLike = ".") -> dict:
    """Where does this lug physically live RIGHT NOW — which git worktree + branch + sha.

    Stamped at creation and refreshed on every mutating write (bump_rev) so a lug
    always carries the worktree it was last touched in. The fleet runs many concurrent
    sessions, each in its own worktree (.worktrees/<name>) on its own branch; a lug
    created/advanced in worktree A on an unmerged branch is invisible from worktree B.
    Recording origin lets a reconciler (lug_worktree_map.py) answer "where is this work
    spread, and which worktree/branch must I check out to handle it?" — instead of work
    silently stranding on a branch nobody merges (the 8-worktree / 7-branch drift, S135).

    Fails soft: outside a git repo, returns the path with null git fields (never raises).
    """
    cwd = str(spoke_path) if spoke_path and str(spoke_path) != "." else os.getcwd()

    def _git(*args):
        try:
            out = subprocess.run(["git", "-C", cwd, *args],
                                 capture_output=True, text=True, timeout=3)
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:
            return None

    # worktree root = top of THIS working tree (each worktree has its own), so
    # .worktrees/<name> resolves to itself rather than the shared main checkout.
    wt_root = _git("rev-parse", "--show-toplevel")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    sha = _git("rev-parse", "--short", "HEAD")
    return {
        "worktree": wt_root,
        "worktree_name": (os.path.basename(wt_root) if wt_root else None),
        "branch": (branch if branch and branch != "HEAD" else None),
        "git_sha": sha,
        "stamped_at": _now_iso(),
    }


def _wai_session_id(spoke_path: str | os.PathLike = ".") -> str:
    """Resolve the current WAI session id: env override, else the most recent
    sessions/ track dir, else a uuid-derived fallback."""
    env = os.environ.get("WAI_SESSION_ID")
    if env:
        return env
    sessions = Path(spoke_path) / "WAI-Spoke" / "sessions"
    try:
        dirs = [d for d in sessions.iterdir() if d.is_dir() and d.name.startswith("session-")]
        if dirs:
            return max(dirs, key=lambda d: d.stat().st_mtime).name
    except (OSError, FileNotFoundError):
        pass
    u8 = _cc_uuid8()
    return f"session-{u8}" if u8 else "session-unknown"


def resolve_attribution(spoke_path: str | os.PathLike = ".", agent: str | None = None) -> tuple[str, str]:
    """Return (actor, kind) — the canonical attribution string + kind.

    actor  = '{session-id}-{cc_uuid8}.{contributor}'  (who/when/where in one string)
    kind   = 'agent' when an agent label is given (autonomous run), else 'user'
    """
    sid = _wai_session_id(spoke_path)
    u8 = _cc_uuid8()
    base = sid if (not u8 or sid.endswith(u8)) else f"{sid}-{u8}"
    if agent:
        return f"{base}.{agent}", "agent"
    return f"{base}.{_git_user() or 'unknown'}", "user"


def resolve_lug_path(lug_id: str) -> Path | None:
    """Find a lug file across all bytype/ folders."""
    if not BYTYPE.exists():
        return None
    for type_dir in BYTYPE.iterdir():
        if not type_dir.is_dir():
            continue
        for status_dir in type_dir.iterdir():
            if not status_dir.is_dir():
                continue
            candidate = status_dir / f"{lug_id}.json"
            if candidate.exists():
                return candidate
    return None


def is_lug_completed(lug_id: str) -> bool:
    """Check if a lug exists in any completed/ or delivered/ folder."""
    if not BYTYPE.exists():
        return False
    for type_dir in BYTYPE.iterdir():
        if not type_dir.is_dir():
            continue
        for done_dir in ("completed", "delivered"):
            candidate = type_dir / done_dir / f"{lug_id}.json"
            if candidate.exists():
                return True
    return False


def lug_exists(lug_id: str) -> bool:
    """Check if a lug exists anywhere in bytype/ (any status)."""
    return resolve_lug_path(lug_id) is not None


def validate_blocked_by(blocked_by: list[str]) -> list[str]:
    """Validate blocked_by IDs at lug creation time. Returns list of warnings."""
    warnings = []
    for bid in blocked_by:
        if is_lug_completed(bid):
            warnings.append(f"blocked_by '{bid}' is already completed — remove reference")
        elif not lug_exists(bid):
            warnings.append(f"blocked_by '{bid}' not found in active lugs — remove or update")
    return warnings


def is_blocked(lug: dict) -> bool:
    """Check if a lug has unresolved blockers in its blocked_by array.

    A blocker only gates if it exists AND is not completed.
    Missing or completed blockers are skipped (with warnings via blocked_reason).
    """
    blocked_by = lug.get("blocked_by", [])
    if not blocked_by:
        return False
    for blocker_id in blocked_by:
        if is_lug_completed(blocker_id):
            continue  # resolved
        if not lug_exists(blocker_id):
            continue  # missing — don't gate on phantom blockers
        return True
    return False


def blocked_reason(lug: dict) -> str:
    """Return human-readable reason why a lug is blocked, or empty string.

    Only reports blockers that actually exist and are unresolved.
    Surfaces warnings for missing/completed refs.
    """
    blocked_by = lug.get("blocked_by", [])
    if not blocked_by:
        return ""
    active_blockers = []
    stale_refs = []
    for bid in blocked_by:
        if is_lug_completed(bid):
            stale_refs.append(f"{bid} (completed)")
        elif not lug_exists(bid):
            stale_refs.append(f"{bid} (missing)")
        else:
            active_blockers.append(bid)
    parts = []
    if active_blockers:
        parts.append(f"blocked by: {', '.join(active_blockers)}")
    if stale_refs:
        parts.append(f"stale blocked_by refs — remove: {', '.join(stale_refs)}")
    return " | ".join(parts)


def evaluate_execute_when(lug: dict, phases: list[dict] | None = None) -> tuple[bool, str]:
    """Evaluate execute_when conditions on a lug.

    Returns (ready, reason):
        ready=True  → all conditions met, lug can dispatch
        ready=False → reason explains what's blocking

    Conditions (all must be satisfied if present):
        all_completed:    every listed lug ID must be in completed/
        any_completed:    at least one listed lug ID must be in completed/
        phase_completed:  all lugs belonging to the named phase must be completed
        manual_gate:      if true, always returns not-ready (requires user override)
    """
    ew = lug.get("execute_when")
    if not ew:
        # No gate — also check legacy blocked_by
        if is_blocked(lug):
            return False, blocked_reason(lug)
        return True, ""

    # Manual gate — always blocks unless overridden
    if ew.get("manual_gate", False):
        return False, "manual gate: requires explicit user approval"

    # all_completed — AND logic
    all_completed = ew.get("all_completed", [])
    if all_completed:
        missing = [lid for lid in all_completed if not is_lug_completed(lid)]
        if missing:
            return False, f"waiting for all: {', '.join(missing)}"

    # any_completed — OR logic
    any_completed = ew.get("any_completed", [])
    if any_completed:
        if not any(is_lug_completed(lid) for lid in any_completed):
            return False, f"waiting for any of: {', '.join(any_completed)}"

    # phase_completed — all members of named phase must be done
    phase_id = ew.get("phase_completed")
    if phase_id and phases:
        phase_members = _get_phase_members(phase_id)
        incomplete = [m for m in phase_members if not is_lug_completed(m)]
        if incomplete:
            return False, f"phase '{phase_id}' incomplete: {', '.join(incomplete[:5])}"

    # Also check legacy blocked_by
    if is_blocked(lug):
        return False, blocked_reason(lug)

    return True, ""


def _get_phase_members(phase_id: str) -> list[str]:
    """Find all lug IDs that declare membership in a given phase."""
    members: list[str] = []
    if not BYTYPE.exists():
        return members
    # Scan all lugs (any status) for phase field
    for type_dir in BYTYPE.iterdir():
        if not type_dir.is_dir():
            continue
        for status_dir in type_dir.iterdir():
            if not status_dir.is_dir():
                continue
            for lug_file in status_dir.glob("*.json"):
                try:
                    data = json.loads(lug_file.read_text())
                    if data.get("phase") == phase_id:
                        members.append(data.get("id", lug_file.stem))
                except (json.JSONDecodeError, OSError):
                    continue
    return members


def get_lug_id(lug: dict) -> str:
    return lug.get("id") or lug.get("i") or "unknown"


def get_lug_type(lug: dict) -> str:
    raw = lug.get("type") or lug.get("ty") or "unknown"
    if isinstance(raw, str) and len(raw) > 30:
        return "unknown"
    return raw.replace(" ", "-").lower()


def get_lug_status(lug: dict) -> str:
    return lug.get("status") or lug.get("s") or "unknown"


def get_lug_title(lug: dict) -> str:
    return lug.get("title") or lug.get("t") or ""


def load_phases_from_state() -> list[dict[str, Any]]:
    """Load phase definitions from WAI-State.json _work_queue.phases."""
    state_file = SPOKE / "WAI-State.json"
    if not state_file.exists():
        return []
    try:
        state = json.loads(state_file.read_text())
        return state.get("_work_queue", {}).get("phases", [])
    except (json.JSONDecodeError, OSError):
        return []


# ---------------------------------------------------------------------------
# v4 lug optimistic concurrency (spec-lug-schema-v4-v1)
# `rev` is a monotonic integer incremented by exactly 1 on every mutating write,
# paired with updated_at. It is the field change_registry.check_rev() reads to
# reject stale-rev writes (last-write-wins BANNED). bump_rev is the single code
# path for the increment; prepare_lug_write wraps the same-spoke concurrency check.
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def bump_rev(lug: dict, now_iso: str | None = None) -> dict:
    """Increment lug['rev'] by exactly 1 (initializing to 1 if absent) and set
    updated_at. The ONLY sanctioned mutating-write path for rev, so the monotonic
    invariant check_rev() relies on always holds. Mutates and returns the lug."""
    cur = lug.get("rev")
    lug["rev"] = (cur + 1) if isinstance(cur, int) else 1
    lug["updated_at"] = now_iso or _now_iso()
    # refresh where this lug now lives — the worktree/branch doing this write is, by
    # definition, where the lug currently is. Keeps origin accurate as work moves
    # between worktrees so reconciliation can always locate it.
    lug["origin"] = resolve_worktree_origin()
    return lug


def prepare_lug_write(lug: dict, write_against_rev: int, now_iso: str | None = None) -> dict:
    """Same-spoke optimistic-concurrency gate for a lug mutation, mirroring
    change_registry.check_rev semantics. `write_against_rev` is the rev the writer
    read before preparing its change.

    Returns:
      {"ok": False, "reason": ...}                  — missing rev (last-write-wins banned)
      {"ok": False, "stale": True, "reason": ...}   — a concurrent session advanced the lug
      {"ok": True, "lug": <bumped>, "next_rev": N}  — applied; rev incremented + updated_at set
    """
    current = lug.get("rev")
    if current is None or write_against_rev is None:
        return {"ok": False, "reason": "missing rev — cannot apply (last-write-wins banned)"}
    if write_against_rev < current:
        return {"ok": False, "stale": True,
                "reason": f"write prepared against rev {write_against_rev} but current is "
                          f"{current} — reconcile required, not silent overwrite"}
    bump_rev(lug, now_iso)
    return {"ok": True, "lug": lug, "next_rev": lug["rev"]}
