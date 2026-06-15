#!/usr/bin/env python3
"""
burn_panel.py — Compact 3–4 line session burn/budget panel for wai-enter.sh.

Reads:
  WAI-Spoke/sessions/session-*/        — session activity by mtime
  WAI-Spoke/model-usage/usage.jsonl    — per-event tokens + cost (optional)
  WAI-Spoke/lugs/bytype/*/in_progress/ — active work load
  tools/sync_retry_queue.jsonl         — pending Supabase syncs

Always exits 0. Output is advisory only.
"""

from __future__ import annotations

import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)

SESSIONS_DIR   = os.path.join(_REPO_ROOT, "WAI-Spoke/sessions")
USAGE_FILE     = os.path.join(_REPO_ROOT, "WAI-Spoke/model-usage/usage.jsonl")
LUGS_BYTYPE    = os.path.join(_REPO_ROOT, "WAI-Spoke/lugs/bytype")
SYNC_QUEUE     = os.path.join(_REPO_ROOT, "tools/sync_retry_queue.jsonl")

DAY_SECONDS  = 24 * 3600
WEEK_SECONDS = 7 * DAY_SECONDS


def _count_sessions_within(window_seconds: int) -> int:
    if not os.path.isdir(SESSIONS_DIR):
        return 0
    cutoff = time.time() - window_seconds
    n = 0
    try:
        for entry in os.listdir(SESSIONS_DIR):
            if not entry.startswith("session-"):
                continue
            path = os.path.join(SESSIONS_DIR, entry)
            try:
                if os.path.getmtime(path) >= cutoff:
                    n += 1
            except OSError:
                pass
    except OSError:
        pass
    return n


def _usage_totals(window_seconds: int) -> tuple[float, int, bool]:
    """Returns (cost_usd, tokens_total, file_present)."""
    if not os.path.isfile(USAGE_FILE):
        return 0.0, 0, False
    cutoff = time.time() - window_seconds
    cost = 0.0
    tokens = 0
    try:
        for line in open(USAGE_FILE):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = ev.get("ts", "")
            try:
                ev_secs = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
            except (ValueError, TypeError):
                continue
            if ev_secs < cutoff:
                continue
            c = ev.get("cost_estimate")
            if isinstance(c, (int, float)):
                cost += float(c)
            for k in ("tokens_in", "tokens_out"):
                v = ev.get(k)
                if isinstance(v, int):
                    tokens += v
    except OSError:
        return 0.0, 0, True
    return cost, tokens, True


def _count_in_progress_lugs() -> int:
    if not os.path.isdir(LUGS_BYTYPE):
        return 0
    n = 0
    try:
        for type_name in os.listdir(LUGS_BYTYPE):
            ip_dir = os.path.join(LUGS_BYTYPE, type_name, "in_progress")
            if not os.path.isdir(ip_dir):
                continue
            for f in os.listdir(ip_dir):
                if f.endswith(".json"):
                    n += 1
    except OSError:
        pass
    return n


def _count_sync_queue() -> int:
    if not os.path.isfile(SYNC_QUEUE):
        return 0
    try:
        with open(SYNC_QUEUE) as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def _fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}k"
    return str(n)


def main() -> int:
    sess_24h = _count_sessions_within(DAY_SECONDS)
    sess_7d  = _count_sessions_within(WEEK_SECONDS)

    cost_24h, tokens_24h, usage_present = _usage_totals(DAY_SECONDS)
    cost_7d,  tokens_7d,  _             = _usage_totals(WEEK_SECONDS)

    in_progress = _count_in_progress_lugs()
    sync_queue  = _count_sync_queue()

    if usage_present:
        burn = f"Burn — 24h: ${cost_24h:.2f} ({_fmt_tokens(tokens_24h)} tokens) | 7d: ${cost_7d:.2f}"
        feed = "Usage feed — live"
    else:
        burn = "Burn — no usage data yet (model_usage_logger.py has not emitted events)"
        feed = "Usage feed — empty"

    sessions = f"Sessions — 24h: {sess_24h} | 7d: {sess_7d}"
    lugs     = f"Active lugs — in_progress: {in_progress} | sync_queue: {sync_queue}"

    print(burn)
    print(sessions)
    print(lugs)
    print(feed)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[burn_panel] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(0)
