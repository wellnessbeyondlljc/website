"""Atomic WAI-State.json read-modify-write under flock.

Prevents concurrent session overwrites of shared fields (session_count,
last_closeout, _savepoint, next_session_recommendation).

Usage:
  python3 tools/state_update.py --spoke-path . --action increment_session_count
  python3 tools/state_update.py --spoke-path . --key _session_state.last_closeout --value '"2026-06-04T12:00:00Z"'
"""
import argparse
import json
import sys
from pathlib import Path

try:
    import fcntl
    HAS_FLOCK = True
except ImportError:
    HAS_FLOCK = False


def _lock_path(spoke_path):
    return Path(spoke_path) / "WAI-Spoke" / "runtime" / "wai-state.lock"


def update_state(spoke_path, mutate_fn):
    """Read-modify-write WAI-State.json under an advisory flock.

    Uses flock() so concurrent sessions merge updates instead of last-writer-wins.
    Falls back gracefully on platforms where fcntl is unavailable.
    """
    spoke = Path(spoke_path)
    state_path = spoke / "WAI-Spoke" / "WAI-State.json"
    lock_path = _lock_path(spoke_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with open(lock_path, "w") as lf:
        if HAS_FLOCK:
            fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            data = json.loads(state_path.read_text())
            data = mutate_fn(data)
            tmp = state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(state_path)
        finally:
            if HAS_FLOCK:
                fcntl.flock(lf, fcntl.LOCK_UN)


def _set_nested(d, keys, value):
    cur = d
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value
    return d


def main():
    ap = argparse.ArgumentParser(description="Atomic WAI-State.json updater")
    ap.add_argument("--spoke-path", default=".")
    ap.add_argument("--action",
                    choices=["increment_session_count", "set_key"],
                    help="Action to perform")
    ap.add_argument("--key", help="Dot-separated key path for set_key action")
    ap.add_argument("--value", help="JSON-encoded value string for set_key action")
    args = ap.parse_args()

    if args.action == "increment_session_count":
        def mutate(d):
            ss = d.setdefault("_session_state", {})
            ss["session_count"] = int(ss.get("session_count", 0)) + 1
            return d
    elif args.action == "set_key":
        if not args.key:
            print("--key is required for set_key action", file=sys.stderr)
            sys.exit(1)
        val = json.loads(args.value) if args.value is not None else None
        keys = args.key.split(".")

        def mutate(d):
            return _set_nested(d, keys, val)
    else:
        print("No action specified. Use --action.", file=sys.stderr)
        sys.exit(1)

    update_state(args.spoke_path, mutate)


if __name__ == "__main__":
    main()
