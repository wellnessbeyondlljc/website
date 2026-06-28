#!/usr/bin/env python3
"""flow_metrics.py — per-flow gate quality metrics with version-anchored baselines.

(impl-gate-storage-topology-v1) Computes, per flow AND per flow-definition
version: approval rate, first-attempt approval rate, halt frequency per step,
and P50 resolution (attempts to reach approved). Crucially the baseline is
ANCHORED at each flow-definition version: when a definition's version
increments, a new baseline row is recorded at that boundary, so a change like
"flow v2 improved approval 55%→82%" is measurable instead of being washed out in
an all-time average.

API:
  compute(events, versions=None) -> {flow_id: {version: metrics}}
  run(events_path=..., flow_defs_dir=..., out_path=..., now_iso=...) -> result
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _patterns_base(spoke_root="."):
    """The patterns/ dir, base-aware. On a v4 spoke this resolves to
    WAI-Harness/spoke/local/patterns; PRE-FIX the hardcoded WAI-Spoke defaults
    read/wrote a nonexistent tree so metrics silently no-op'd
    (impl-fix-p2-v3noop-sweep-v1)."""
    try:
        from wai_paths import resolve_wai_root
        root, mode = resolve_wai_root(str(spoke_root))
        if root and mode != "none":
            return os.path.join(root, "patterns")
    except Exception:
        pass
    return os.path.join(spoke_root, "WAI-Spoke", "patterns")  # v3 fallback


_PATTERNS = _patterns_base()
_DEFAULT_EVENTS = os.path.join(_PATTERNS, "gate-log.jsonl")
_DEFAULT_FLOW_DEFS = os.path.join(_PATTERNS, "flow-definitions")
_DEFAULT_OUT = os.path.join(_PATTERNS, "flow-metrics.jsonl")


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _p50(values):
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def compute(events):
    """Group gate events by (flow_id, version) and compute metrics per window.
    Each event is expected to carry flow_id, step_id, attempt, disposition, and
    flow_version (the version of the definition in force when it was emitted)."""
    groups = {}
    for e in events:
        key = (e.get("flow_id"), e.get("flow_version", 1))
        groups.setdefault(key, []).append(e)

    out = {}
    for (flow_id, version), evs in groups.items():
        terminal = [e for e in evs if e.get("disposition") in ("approved", "escalate")]
        approved = [e for e in terminal if e.get("disposition") == "approved"]
        approval_rate = round(len(approved) / len(terminal), 3) if terminal else None
        first_attempt = [e for e in approved if int(e.get("attempt", 1)) == 1]
        first_rate = round(len(first_attempt) / len(terminal), 3) if terminal else None
        halts = {}
        for e in evs:
            if e.get("disposition") == "halted":
                halts[e.get("step_id")] = halts.get(e.get("step_id"), 0) + 1
        resolution_attempts = [int(e.get("attempt", 1)) for e in approved]
        out.setdefault(flow_id, {})[version] = {
            "flow_id": flow_id, "version": version,
            "terminal_count": len(terminal),
            "approval_rate": approval_rate,
            "first_attempt_approval_rate": first_rate,
            "halt_frequency_per_step": halts,
            "p50_resolution_attempts": _p50(resolution_attempts),
        }
    return out


def _current_versions(flow_defs_dir):
    cur = {}
    for p in glob.glob(os.path.join(flow_defs_dir, "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (ValueError, OSError):
            continue
        cur[d.get("flow_id")] = d.get("version", 1)
    return cur


def run(events_path=_DEFAULT_EVENTS,
        flow_defs_dir=_DEFAULT_FLOW_DEFS,
        out_path=_DEFAULT_OUT, now_iso=None):
    events = _read_jsonl(events_path)
    metrics = compute(events)
    current = _current_versions(flow_defs_dir)

    # baseline anchoring: a baseline row is recorded the first time we see a
    # (flow, version) pair — i.e. on a version bump a NEW baseline is created.
    existing_baselines = set()
    for row in _read_jsonl(out_path):
        if row.get("kind") == "baseline":
            existing_baselines.add((row.get("flow_id"), row.get("version")))

    new_rows, new_baselines = [], 0
    for flow_id, by_ver in metrics.items():
        for version, m in by_ver.items():
            new_rows.append({"kind": "metrics", "computed_at": now_iso, **m})
            key = (flow_id, version)
            if key not in existing_baselines:
                new_rows.append({"kind": "baseline", "flow_id": flow_id, "version": version,
                                 "anchored_at": now_iso, "approval_rate": m["approval_rate"],
                                 "is_current_version": current.get(flow_id) == version})
                existing_baselines.add(key)
                new_baselines += 1

    with open(out_path, "a", encoding="utf-8") as f:
        for r in new_rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    return {"metrics_rows": sum(len(v) for v in metrics.values()),
            "new_baselines": new_baselines, "flows": list(metrics.keys())}


def main(argv=None):
    ap = argparse.ArgumentParser(description="compute per-flow gate metrics + baselines")
    ap.add_argument("--events-path", default=_DEFAULT_EVENTS)
    ap.add_argument("--flow-defs-dir", default=_DEFAULT_FLOW_DEFS)
    ap.add_argument("--out-path", default=_DEFAULT_OUT)
    ap.add_argument("--now-iso", default=None)
    a = ap.parse_args(argv)
    res = run(a.events_path, a.flow_defs_dir, a.out_path, a.now_iso)
    print(f"[flow_metrics] {res}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
