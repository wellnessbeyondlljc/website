#!/usr/bin/env python3
"""
supabase_lug_sync.py — Fire-and-forget upsert of a single lug JSON file to Supabase.

Usage (from the post-tool-use hook):
  python3 tools/supabase_lug_sync.py WAI-Spoke/lugs/bytype/epic/open/epic-xyz.json

Environment:
  SUPABASE_REST  — Supabase REST base URL  (e.g. https://<project>.supabase.co/rest/v1)
  SUPABASE_KEY   — Supabase service_role key (hub) or anon key (spoke)
  WHEEL_ID       — This spoke's wheel_id (fallback: read from WAI-State.json)

If SUPABASE_REST/KEY are unset OR the POST fails, the lug path is appended to
tools/sync_retry_queue.jsonl so a later flush can replay it. Exit status is
always 0 — this script is advisory and must never block the agent or hook.
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SUPABASE_REST = os.environ.get("SUPABASE_REST", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
WHEEL_ID_ENV = os.environ.get("WHEEL_ID", "")

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
RETRY_QUEUE_PATH = os.path.join(_REPO_ROOT, "tools/sync_retry_queue.jsonl")


def _state_path():
    """Locate WAI-State.json, base-aware. On a v4 spoke this resolves to
    WAI-Harness/spoke/local/WAI-State.json; PRE-FIX the hardcoded WAI-Spoke
    path read a nonexistent tree so wheel_id never resolved from state
    (impl-fix-p2-v3noop-sweep-v1). _REPO_ROOT is WAI-Harness/spoke/managed, so
    the spoke root (the dir containing WAI-Harness/) is three levels up."""
    spoke_root = os.path.dirname(os.path.dirname(os.path.dirname(_REPO_ROOT)))
    try:
        from wai_paths import resolve_wai_root
        root, mode = resolve_wai_root(spoke_root)
        if root and mode != "none":
            return os.path.join(root, "WAI-State.json")
    except Exception:
        pass
    return os.path.join(_REPO_ROOT, "WAI-Spoke/WAI-State.json")  # v3 fallback


STATE_PATH = _state_path()


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _resolve_wheel_id() -> str:
    if WHEEL_ID_ENV:
        return WHEEL_ID_ENV
    if os.path.exists(STATE_PATH):
        try:
            state = json.load(open(STATE_PATH))
            wheel = state.get("wheel", {})
            return wheel.get("wheel_id") or wheel.get("spoke_id") or ""
        except Exception:
            pass
    return ""


def _build_row(lug: dict, wheel_id: str, raw_path: str) -> dict:
    """Project a lug JSON into the `lugs` table column shape."""
    row = {
        "id": lug.get("id") or lug.get("i") or "",
        "wheel_id": wheel_id,
        "ty": lug.get("type") or lug.get("ty") or "unknown",
        "status": lug.get("status") or lug.get("s") or "unknown",
        "priority": lug.get("priority"),
        "impact": lug.get("impact") if isinstance(lug.get("impact"), int) else None,
        "routed_to": lug.get("routed_to"),
        "title": lug.get("title") or lug.get("t") or "",
        "one_liner": lug.get("one_liner"),
        "perceive": lug.get("perceive"),
        "execute": lug.get("execute"),
        "verify": lug.get("verify"),
        "gb": lug.get("gb"),
        "created_at": lug.get("created_at") or lug.get("ca"),
        "updated_at": lug.get("updated_at") or _now_iso(),
        "completed_at": lug.get("completed_at") or lug.get("closed_at"),
        "outcome": lug.get("outcome"),
        "superseded_by": lug.get("superseded_by"),
        "raw_path": raw_path,
    }
    return {k: v for k, v in row.items() if v is not None and v != ""}


def _queue_retry(lug_path: str, reason: str) -> None:
    os.makedirs(os.path.dirname(RETRY_QUEUE_PATH), exist_ok=True)
    entry = {"ts": _now_iso(), "path": lug_path, "reason": reason}
    with open(RETRY_QUEUE_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _post_upsert(row: dict) -> bool:
    """POST upsert to lugs table. Returns True on success."""
    url = f"{SUPABASE_REST}/lugs?on_conflict=id"
    data = json.dumps(row).encode()
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            return resp.status in (200, 201, 204)
    except urllib.error.HTTPError as e:
        print(f"[supabase_lug_sync] HTTP {e.code}: {e.read().decode()[:200]}",
              file=sys.stderr)
        return False
    except Exception as e:
        print(f"[supabase_lug_sync] {type(e).__name__}: {e}", file=sys.stderr)
        return False


def sync_lug_file(lug_path: str) -> bool:
    if not os.path.isfile(lug_path):
        _queue_retry(lug_path, "file_missing")
        return False
    try:
        with open(lug_path) as f:
            lug = json.load(f)
    except json.JSONDecodeError as e:
        _queue_retry(lug_path, f"invalid_json: {e}")
        return False

    if not SUPABASE_REST or not SUPABASE_KEY:
        _queue_retry(lug_path, "no_credentials")
        return False

    wheel_id = _resolve_wheel_id()
    if not wheel_id:
        _queue_retry(lug_path, "no_wheel_id")
        return False

    raw_path = os.path.relpath(lug_path, _REPO_ROOT)
    row = _build_row(lug, wheel_id, raw_path)
    if not row.get("id"):
        _queue_retry(lug_path, "no_lug_id")
        return False

    ok = _post_upsert(row)
    if not ok:
        _queue_retry(lug_path, "post_failed")
    return ok


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: supabase_lug_sync.py <lug_json_path>", file=sys.stderr)
        return 0  # Advisory only — never block.
    sync_lug_file(sys.argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
