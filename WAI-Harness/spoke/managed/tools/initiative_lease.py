#!/usr/bin/env python3
"""Initiative leasing — file-based atomic initiative checkout with TTL.

Mirrors lug_lease.py exactly but operates on initiative-level claiming.
Backed by WAI-Spoke/runtime/initiative-claims.json (gitignored via runtime/).

Atomicity: a claim is acquired by first taking an O_EXCL lock file, then
doing a read-modify-write of the store and replacing it atomically via
os.replace. A second concurrent claim on a live (unexpired) lease is rejected.

Claim record shape (stored under store["<initiative_id>"]):
    {
        "initiative_id": str,
        "held_by": str,           # session_id
        "held_at": str,           # ISO-8601 UTC
        "lease_ttl_hours": int,   # default 8
        "worktree_path": str,     # path to git worktree for this session (may be "")
    }

Public API:
    claim(initiative_id, session_id, worktree_path="", ttl_hours=8) -> bool
    release(initiative_id, session_id) -> bool
    is_held(initiative_id) -> bool                  # live (unexpired) only
    held_by(initiative_id) -> Optional[str]
    sweep_expired() -> list[str]                    # released initiative_ids
    active_claims() -> list[dict]                   # live claims (auto-sweeps first)
    active_leases = active_claims                   # alias for backward compat

All functions accept an optional `store_path` for testing.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_TTL_HOURS = 8

_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_STORE = _FRAMEWORK_ROOT / "WAI-Spoke" / "runtime" / "initiative-claims.json"

_LOCK_TIMEOUT_SECONDS = 5.0
_LOCK_POLL_SECONDS = 0.02


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _store_path(store_path: Optional[str]) -> Path:
    return Path(store_path) if store_path else _DEFAULT_STORE


def _parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def _is_expired(record: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    """A record is expired if held_at + lease_ttl_hours <= now."""
    now = now or _now()
    held_at = _parse_dt(record.get("held_at", ""))
    if held_at is None:
        return True
    ttl = record.get("lease_ttl_hours", DEFAULT_TTL_HOURS)
    try:
        ttl = int(ttl)
    except (TypeError, ValueError):
        ttl = DEFAULT_TTL_HOURS
    return held_at + timedelta(hours=ttl) <= now


class _FileLock:
    """Minimal cross-process lock via O_EXCL lock file beside the store."""

    def __init__(self, target: Path):
        self.lock_path = target.with_suffix(target.suffix + ".lock")
        self._fd: Optional[int] = None

    def __enter__(self) -> "_FileLock":
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + _LOCK_TIMEOUT_SECONDS
        while True:
            try:
                self._fd = os.open(
                    str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
                return self
            except FileExistsError:
                try:
                    age = time.time() - self.lock_path.stat().st_mtime
                    if age > _LOCK_TIMEOUT_SECONDS * 2:
                        os.unlink(self.lock_path)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire initiative lease lock: {self.lock_path}"
                    )
                time.sleep(_LOCK_POLL_SECONDS)

    def __exit__(self, *_exc: Any) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        try:
            os.unlink(self.lock_path)
        except FileNotFoundError:
            pass


def _read_store(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text() or "{}")
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_store(path: Path, store: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(store, indent=2) + "\n")
    os.replace(tmp, path)


def claim(
    initiative_id: str,
    session_id: str,
    worktree_path: str = "",
    ttl_hours: int = DEFAULT_TTL_HOURS,
    store_path: Optional[str] = None,
) -> bool:
    """Atomically claim an initiative. Returns True if acquired, False if rejected.

    Rejected only when a live (unexpired) lease is held by a different session.
    Re-claiming an initiative you already hold refreshes the lease and updates worktree_path.
    """
    if not initiative_id or not session_id:
        return False
    path = _store_path(store_path)
    with _FileLock(path):
        store = _read_store(path)
        existing = store.get(initiative_id)
        if existing and not _is_expired(existing):
            if existing.get("held_by") != session_id:
                return False
        store[initiative_id] = {
            "initiative_id": initiative_id,
            "held_by": session_id,
            "held_at": _now().isoformat(),
            "lease_ttl_hours": int(ttl_hours),
            "worktree_path": worktree_path,
        }
        _write_store(path, store)
        return True


def release(
    initiative_id: str, session_id: str, store_path: Optional[str] = None
) -> bool:
    """Release a lease held by session_id. Returns True if a lease was removed.

    Refuses to release a live lease held by a different session.
    """
    path = _store_path(store_path)
    with _FileLock(path):
        store = _read_store(path)
        existing = store.get(initiative_id)
        if not existing:
            return False
        if not _is_expired(existing) and existing.get("held_by") != session_id:
            return False
        del store[initiative_id]
        _write_store(path, store)
        return True


def is_held(initiative_id: str, store_path: Optional[str] = None) -> bool:
    """True iff a live (unexpired) lease exists for initiative_id."""
    path = _store_path(store_path)
    store = _read_store(path)
    record = store.get(initiative_id)
    if not record:
        return False
    return not _is_expired(record)


def held_by(initiative_id: str, store_path: Optional[str] = None) -> Optional[str]:
    """Return the session_id holding a live lease, or None."""
    path = _store_path(store_path)
    store = _read_store(path)
    record = store.get(initiative_id)
    if record and not _is_expired(record):
        return record.get("held_by")
    return None


def sweep_expired(store_path: Optional[str] = None) -> List[str]:
    """Remove all expired leases. Returns the list of released initiative_ids."""
    path = _store_path(store_path)
    with _FileLock(path):
        store = _read_store(path)
        now = _now()
        released = [iid for iid, rec in store.items() if _is_expired(rec, now)]
        if released:
            for iid in released:
                del store[iid]
            _write_store(path, store)
        return released


def active_claims(store_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return live claims with computed expires_at. Sweeps expired first."""
    path = _store_path(store_path)
    sweep_expired(store_path)
    store = _read_store(path)
    out: List[Dict[str, Any]] = []
    for iid, rec in store.items():
        held_at_dt = _parse_dt(rec.get("held_at", ""))
        ttl = rec.get("lease_ttl_hours", DEFAULT_TTL_HOURS)
        try:
            ttl = int(ttl)
        except (TypeError, ValueError):
            ttl = DEFAULT_TTL_HOURS
        expires_at = (
            (held_at_dt + timedelta(hours=ttl)).isoformat() if held_at_dt else None
        )
        out.append(
            {
                "initiative_id": iid,
                "held_by": rec.get("held_by"),
                "held_at": rec.get("held_at"),
                "lease_ttl_hours": ttl,
                "worktree_path": rec.get("worktree_path", ""),
                "expires_at": expires_at,
            }
        )
    out.sort(key=lambda r: r["initiative_id"])
    return out


# Backward-compat alias
active_leases = active_claims


def _main(argv: List[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Initiative leasing CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("claim")
    c.add_argument("initiative_id")
    c.add_argument("session_id")
    c.add_argument("--ttl-hours", type=int, default=DEFAULT_TTL_HOURS)
    c.add_argument("--worktree-path", default="")

    r = sub.add_parser("release")
    r.add_argument("initiative_id")
    r.add_argument("session_id")

    h = sub.add_parser("is-held")
    h.add_argument("initiative_id")

    hb = sub.add_parser("held-by")
    hb.add_argument("initiative_id")

    sub.add_parser("sweep")
    sub.add_parser("claims")

    args = p.parse_args(argv)
    if args.cmd == "claim":
        ok = claim(args.initiative_id, args.session_id, args.worktree_path, args.ttl_hours)
        print(json.dumps({"claimed": ok}))
        return 0 if ok else 1
    if args.cmd == "release":
        ok = release(args.initiative_id, args.session_id)
        print(json.dumps({"released": ok}))
        return 0 if ok else 1
    if args.cmd == "is-held":
        print(json.dumps({"held": is_held(args.initiative_id)}))
        return 0
    if args.cmd == "held-by":
        print(json.dumps({"held_by": held_by(args.initiative_id)}))
        return 0
    if args.cmd == "sweep":
        print(json.dumps({"released": sweep_expired()}))
        return 0
    if args.cmd == "claims":
        print(json.dumps(active_claims(), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
