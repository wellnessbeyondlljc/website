#!/usr/bin/env python3
"""
emit_activity_event.py — Post a single activity event to Supabase (or queue it locally).

Usage (from wakeup/closeout skills):
  python3 tools/emit_activity_event.py '{"event_type": "session_start", "session_id": "...", ...}'

Environment:
  SUPABASE_REST  — Supabase REST base URL  (e.g. https://<project>.supabase.co/rest/v1)
  SUPABASE_KEY   — Supabase service_role key
  WHEEL_ID       — This spoke's wheel_id

If SUPABASE_REST is unset, the event is written to the local queue file
(WAI-Spoke/runtime/activity-events-queue.jsonl) for batch delivery at closeout.
"""

import json
import os
import sys
import datetime
import urllib.request
import urllib.error

SUPABASE_REST = os.environ.get("SUPABASE_REST", "")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "")
WHEEL_ID      = os.environ.get("WHEEL_ID", "")

_HERE      = os.path.dirname(os.path.abspath(__file__))


def _spoke_root() -> str:
    """Walk up from this tool to the spoke ROOT. tools/ sits at
    WAI-Harness/spoke/managed/tools in v4, so the root is several levels up — not
    dirname(_HERE). Prefer the nearest WAI-Harness-bearing ancestor (the v4 root);
    a stray managed/WAI-Spoke/reference dir must NOT be mistaken for the root, so
    a WAI-Spoke-only match is a fallback used only when no WAI-Harness ancestor
    exists (a pure v3 spoke)."""
    d = _HERE
    v3_root = None
    while True:
        if os.path.isdir(os.path.join(d, "WAI-Harness")):
            return d  # v4 root wins
        if v3_root is None and os.path.isdir(os.path.join(d, "WAI-Spoke")):
            v3_root = d
        parent = os.path.dirname(d)
        if parent == d:
            return v3_root or os.path.dirname(_HERE)  # v3 root, else legacy
        d = parent


def _base(spoke_root: str) -> str:
    """Resolve the spoke working base, base-aware. On a v4 spoke this routes to
    WAI-Harness/spoke/local instead of the nonexistent WAI-Spoke tree, so events
    queue/read on the live tree (impl-fix-p2-v3noop-sweep-v1)."""
    try:
        sys.path.insert(0, _HERE)
        import wai_paths
        root, mode = wai_paths.resolve_wai_root(str(spoke_root))
        if root and mode != "none":
            return root
    except Exception:
        pass
    return os.path.join(spoke_root, "WAI-Spoke")  # last-resort v3 fallback


_BASE      = _base(_spoke_root())
QUEUE_PATH = os.path.join(_BASE, "runtime/activity-events-queue.jsonl")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _resolve_wheel_id() -> str:
    if WHEEL_ID:
        return WHEEL_ID
    state_path = os.path.join(_BASE, "WAI-State.json")
    if os.path.exists(state_path):
        try:
            state = json.load(open(state_path))
            return state.get("wheel", {}).get("wheel_id", "")
        except Exception:
            pass
    return ""


def post_event(event: dict) -> bool:
    """POST event to Supabase REST. Returns True on success."""
    url = f"{SUPABASE_REST}/activity_events"
    data = json.dumps(event).encode()
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status in (200, 201, 204)
    except urllib.error.HTTPError as e:
        print(f"[emit_activity_event] HTTP {e.code}: {e.read().decode()[:120]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[emit_activity_event] Error: {e}", file=sys.stderr)
        return False


def queue_event(event: dict):
    """Append event to local queue file (no network required)."""
    os.makedirs(os.path.dirname(QUEUE_PATH), exist_ok=True)
    with open(QUEUE_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")


def emit(event: dict) -> bool:
    """Emit event: live POST if credentials present, queue otherwise."""
    # Fill defaults
    event.setdefault("ts", _now_iso())
    event.setdefault("wheel_id", _resolve_wheel_id())

    if SUPABASE_REST and SUPABASE_KEY:
        ok = post_event(event)
        if not ok:
            # Fall back to queue on failure
            queue_event(event)
        return ok
    else:
        # No credentials — queue silently
        queue_event(event)
        return True  # not a failure; will be delivered at next sync


def batch_flush(queue_path: str = QUEUE_PATH) -> tuple:
    """
    Read all events from the local queue and POST them to Supabase in one request.
    Returns (flushed_count, failed_count).
    Clears the queue file on full success. On partial failure, leaves unposted events.
    """
    if not SUPABASE_REST or not SUPABASE_KEY:
        return 0, 0  # No credentials — leave queue intact

    if not os.path.exists(queue_path):
        return 0, 0

    events = []
    with open(queue_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not events:
        return 0, 0

    # Drop malformed events (empty event_type) and normalize to uniform keys.
    # Supabase batch POST requires all objects to have identical keys.
    # Use the intersection of known-good schema columns to avoid cache-miss errors.
    events = [e for e in events if e.get("event_type")]
    if not events:
        return 0, 0
    # Use the safe base columns that exist in the original table schema
    SAFE_COLS = ["ts", "wheel_id", "session_id", "session_kind", "event_type",
                 "duration_ms", "outcome", "lug_refs"]
    events = [{col: e.get(col) for col in SAFE_COLS} for e in events]

    url = f"{SUPABASE_REST.rstrip('/')}/activity_events"
    data = json.dumps(events).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status in (200, 201):
                open(queue_path, "w").close()  # clear queue
                return len(events), 0
    except urllib.error.HTTPError:
        pass
    except urllib.error.URLError:
        pass
    return 0, len(events)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--flush":
        ok, fail = batch_flush()
        print(f"Flushed {ok} events, {fail} failed.")
        sys.exit(0 if fail == 0 else 1)
    if len(sys.argv) < 2:
        print("Usage: emit_activity_event.py '<json_event>' | --flush", file=sys.stderr)
        sys.exit(1)
    try:
        ev = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    ok = emit(ev)
    sys.exit(0 if ok else 1)
