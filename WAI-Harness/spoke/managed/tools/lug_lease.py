#!/usr/bin/env python3
"""Lug leasing — file-based atomic lug checkout with TTL.

Generalizes the chain-claim mechanism to arbitrary lugs at lug granularity.
There is no Supabase / wai_claims table in the framework spoke, so this is a
fresh, self-contained, file-based implementation backed by a single JSON
store at WAI-Spoke/runtime/claims-local.json.

Atomicity: a claim is acquired by first taking an O_EXCL lock file, then
doing a read-modify-write of the store and replacing it atomically via
os.replace. A second concurrent claim on a live (unexpired) lease is rejected.

Claim record shape (stored under store["<lug_id>"]):
    {
        "lug_id": str,
        "held_by": str,          # session_id
        "held_at": str,          # ISO-8601 UTC
        "lease_ttl_hours": int,  # default 4
    }

Public API:
    claim(lug_id, session_id, ttl_hours=4) -> bool
    release(lug_id, session_id) -> bool
    is_held(lug_id) -> bool                 # live (unexpired) only
    sweep_expired() -> list[str]            # released lug_ids
    active_leases() -> list[dict]           # live leases (auto-sweeps first)

All functions accept an optional `store_path` for testing.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wai_paths import resolve_wai_root  # noqa: E402  (v3/v4 resolver)

DEFAULT_TTL_HOURS = 4

# Default store location, resolved relative to the framework root (this file
# lives in <root>/tools/lug_lease.py).
_FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent


def _spoke_base() -> Path:
    """Resolve the live spoke working-base (v4: WAI-Harness/spoke/local; v3:
    WAI-Spoke), independent of nesting depth. PRE-FIX the store lived under a
    hardcoded 'WAI-Spoke/runtime' -> on a v4 spoke every claim/release/sweep hit a
    phantom store, so leasing silently never persisted (impl-fix-p2-v3noop-sweep-v1)."""
    start = Path(__file__).resolve()
    for anc in start.parents:
        if (anc / "WAI-Harness" / "spoke" / "local").is_dir():
            base, mode = resolve_wai_root(str(anc))
            if base and mode != "none":
                return Path(base)
    for anc in start.parents:
        if (anc / "WAI-Spoke").is_dir():
            return anc / "WAI-Spoke"
    return _FRAMEWORK_ROOT / "WAI-Spoke"


_DEFAULT_STORE = _spoke_base() / "runtime" / "claims-local.json"

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
        # No valid timestamp -> treat as expired so it can be reclaimed.
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
                # Stale-lock guard: if the lock is older than the timeout,
                # steal it (the prior holder almost certainly crashed).
                try:
                    age = time.time() - self.lock_path.stat().st_mtime
                    if age > _LOCK_TIMEOUT_SECONDS * 2:
                        os.unlink(self.lock_path)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire lease lock: {self.lock_path}"
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
    lug_id: str,
    session_id: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    store_path: Optional[str] = None,
) -> bool:
    """Atomically claim a lug. Returns True if acquired, False if rejected.

    Rejected only when a live (unexpired) lease is held by a different
    session. Re-claiming a lug you already hold refreshes the lease.
    """
    if not lug_id or not session_id:
        return False
    path = _store_path(store_path)
    with _FileLock(path):
        store = _read_store(path)
        existing = store.get(lug_id)
        if existing and not _is_expired(existing):
            if existing.get("held_by") != session_id:
                return False
            # Same holder re-claiming -> refresh below.
        store[lug_id] = {
            "lug_id": lug_id,
            "held_by": session_id,
            "held_at": _now().isoformat(),
            "lease_ttl_hours": int(ttl_hours),
        }
        _write_store(path, store)
        return True


def release(lug_id: str, session_id: str, store_path: Optional[str] = None) -> bool:
    """Release a lease held by session_id. Returns True if a lease was removed.

    Refuses to release a live lease held by a different session.
    """
    path = _store_path(store_path)
    with _FileLock(path):
        store = _read_store(path)
        existing = store.get(lug_id)
        if not existing:
            return False
        if (
            not _is_expired(existing)
            and existing.get("held_by") != session_id
        ):
            return False
        del store[lug_id]
        _write_store(path, store)
        return True


def is_held(lug_id: str, store_path: Optional[str] = None) -> bool:
    """True iff a live (unexpired) lease exists for lug_id."""
    path = _store_path(store_path)
    store = _read_store(path)
    record = store.get(lug_id)
    if not record:
        return False
    return not _is_expired(record)


def held_by(lug_id: str, store_path: Optional[str] = None) -> Optional[str]:
    """Return the session_id holding a live lease, or None."""
    path = _store_path(store_path)
    store = _read_store(path)
    record = store.get(lug_id)
    if record and not _is_expired(record):
        return record.get("held_by")
    return None


def sweep_expired(store_path: Optional[str] = None) -> List[str]:
    """Remove all expired leases. Returns the list of released lug_ids."""
    path = _store_path(store_path)
    with _FileLock(path):
        store = _read_store(path)
        now = _now()
        released = [lid for lid, rec in store.items() if _is_expired(rec, now)]
        if released:
            for lid in released:
                del store[lid]
            _write_store(path, store)
        return released


def active_leases(store_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return live leases with computed expires_at. Sweeps expired first."""
    path = _store_path(store_path)
    sweep_expired(store_path)
    store = _read_store(path)
    out: List[Dict[str, Any]] = []
    for lid, rec in store.items():
        held_at = _parse_dt(rec.get("held_at", ""))
        ttl = rec.get("lease_ttl_hours", DEFAULT_TTL_HOURS)
        try:
            ttl = int(ttl)
        except (TypeError, ValueError):
            ttl = DEFAULT_TTL_HOURS
        expires_at = (held_at + timedelta(hours=ttl)).isoformat() if held_at else None
        out.append(
            {
                "lug_id": lid,
                "held_by": rec.get("held_by"),
                "held_at": rec.get("held_at"),
                "lease_ttl_hours": ttl,
                "expires_at": expires_at,
            }
        )
    out.sort(key=lambda r: r["lug_id"])
    return out


def _main(argv: List[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Lug leasing CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("claim")
    c.add_argument("lug_id")
    c.add_argument("session_id")
    c.add_argument("--ttl-hours", type=int, default=DEFAULT_TTL_HOURS)

    r = sub.add_parser("release")
    r.add_argument("lug_id")
    r.add_argument("session_id")

    h = sub.add_parser("is-held")
    h.add_argument("lug_id")

    sub.add_parser("sweep")
    sub.add_parser("active")

    args = p.parse_args(argv)
    if args.cmd == "claim":
        ok = claim(args.lug_id, args.session_id, args.ttl_hours)
        print(json.dumps({"claimed": ok}))
        return 0 if ok else 1
    if args.cmd == "release":
        ok = release(args.lug_id, args.session_id)
        print(json.dumps({"released": ok}))
        return 0 if ok else 1
    if args.cmd == "is-held":
        print(json.dumps({"held": is_held(args.lug_id)}))
        return 0
    if args.cmd == "sweep":
        print(json.dumps({"released": sweep_expired()}))
        return 0
    if args.cmd == "active":
        print(json.dumps(active_leases(), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
