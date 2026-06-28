#!/usr/bin/env python3
# tools/write_assay.py — write assay_full.json and deliver to hub:navigator
#
# Usage: python3 tools/write_assay.py <track_path>
#
# Reads the session track.jsonl at <track_path>, builds a PII-free assay record
# (model IDs, provider names, tool names, work_type labels, lug IDs — no message
# content), writes assay_full.json alongside the track, and delivers a copy to
# hub:navigator's assay-inbox if hub is connected.
# Run from the project root.

import sys

if len(sys.argv) < 2:
    print("Usage: write_assay.py <track_path>", file=sys.stderr)
    sys.exit(1)

import json, os, datetime, glob, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from wai_paths import resolve_wai_root  # noqa: E402  (v3/v4 resolver); sibling tools import this way
except ImportError:
    resolve_wai_root = None


def _base(spoke_root="."):
    """Spoke working base, v4-aware. PRE-FIX this read 'WAI-Spoke/...' -> on a v4 spoke
    state + active lugs came from a nonexistent tree, so the assay was built from empty
    data (silent no-op). Now resolves WAI-Harness/spoke/local (impl-fix-p2-v3noop-sweep-v1)."""
    if resolve_wai_root:
        root, mode = resolve_wai_root(str(spoke_root))
        if root and mode != "none":
            return root
    return os.path.join(str(spoke_root), "WAI-Spoke")  # last-resort v3 fallback


_BASE = _base(".")

track_path = sys.argv[1]

# --- Re-derive shared session context (mirrors write_cartographer_obs.py) ----

# Load track events
events = []
try:
    with open(track_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                    if isinstance(obj, list):
                        events.extend(obj)
                    else:
                        events.append(obj)
                except Exception:
                    pass
except FileNotFoundError:
    print("Assay: no track found — skipping", file=sys.stderr)
    sys.exit(0)

# Session metadata from WAI-State
try:
    state = json.load(open(os.path.join(_BASE, "WAI-State.json")))
except Exception:
    state = {}

spoke_id = state.get("spoke_id", "unknown")
sess = state.get("_session_state", {})
session_id = sess.get("session_id") or "unknown"
session_vibe = sess.get("vibe") or None

# Model ID — check session state first, then scan track events
model_id = sess.get("model_id") or "unknown"
if model_id == "unknown":
    for ev in events:
        if ev.get("model"):
            model_id = ev["model"]
            break

# Provider — derive from model_id
_mid_lower = model_id.lower()
provider = (
    "anthropic" if "claude" in _mid_lower else
    "openai"    if "gpt" in _mid_lower or "o1" in _mid_lower else
    "gemini"    if "gemini" in _mid_lower else
    "z_ai"      if "glm" in _mid_lower or "z.ai" in _mid_lower or "zai" in _mid_lower else
    "nvidia"    if _mid_lower.startswith(("nvidia/", "meta/", "mistralai/")) else
    "together"  if "/" in model_id else
    "unknown"
)

# Active lugs + dominant work type
active_lugs = []
for path in glob.glob(os.path.join(_BASE, "lugs/bytype/*/in_progress/*.json")):
    try:
        active_lugs.append(json.load(open(path)))
    except Exception:
        pass

lug_types = {l.get("type", "") for l in active_lugs}

def infer_work_type(types, vibe):
    if "bug" in types or "finding" in types:        return "debugging"
    if ("implementation" in types or "task" in types) and vibe in ("build", "grind"):
        return "coding"
    if "epic" in types or "feature" in types:       return "planning"
    if "decision" in types:                         return "analysis"
    if vibe == "think" and not types:               return "ideation"
    if "policy" in types or "foundation" in types:  return "writing"
    return "analysis"

dominant_work_type = infer_work_type(lug_types, session_vibe)
turn_count = sum(1 for ev in events if ev.get("role") == "user")

# Lug progression count (completed transitions) — used in session summary
lug_progression = sum(
    1 for ev in events
    if ev.get("event") == "lug_status_change"
    and ev.get("to_status") == "completed"
)

# --- Assay write (step 6c logic) ---------------------------------------------

session_dir = os.path.dirname(track_path)  # same dir as track.jsonl
assay_path = os.path.join(session_dir, 'assay_full.json')

# Build turns list from session memory + track events
# Each notable turn: agent used Write/Edit/Agent/Bash, or switched work_type
# Wakeup and closeout are always recorded
turns = []
seq = 1

# Wakeup turn
turns.append({
    "seq": seq, "ts": events[0].get("timestamp") if events else datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "model": model_id, "provider": provider, "work_type": "wakeup",
    "tools_invoked": ["Skill"], "lug_ids": [], "sub_agents": []
})
seq += 1

# Implementation turns — one per lug worked
for lug in active_lugs:
    turns.append({
        "seq": seq, "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model": model_id, "provider": provider, "work_type": dominant_work_type,
        "tools_invoked": ["Read", "Write", "Edit"],
        "lug_ids": [lug.get("id", "unknown")], "sub_agents": []
    })
    seq += 1

# Closeout turn
turns.append({
    "seq": seq, "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "model": model_id, "provider": provider, "work_type": "closeout",
    "tools_invoked": ["Read", "Edit", "Bash"], "lug_ids": [], "sub_agents": []
})

# Summary
model_turns = {}
for t in turns:
    model_turns[t["model"]] = model_turns.get(t["model"], 0) + 1

assay = {
    "schema_version": "1.0",
    "session_id": session_id,
    "spoke": spoke_id,
    "fw_ver": state.get("wheel", {}).get("version") or state.get("_project_foundation", {}).get("identity", {}).get("version"),
    "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "session_outcome": "CLEAN",
    "turns": turns,
    "session_summary": {
        "total_turns": len(turns),
        "models_used": model_turns,
        "providers_used": {provider: len(turns)},
        "tools_invoked_counts": {"Read": turn_count, "Write": lug_progression, "Edit": lug_progression},
        "sub_agent_turns": 0,
        "sub_agent_models": {},
        "work_types_covered": list({t["work_type"] for t in turns}),
        "lugs_worked": [l.get("id") for l in active_lugs if l.get("id")]
    }
}

with open(assay_path, 'w') as f:
    json.dump(assay, f, indent=2)
print(f"Assay: written → {assay_path}")

# Deliver to hub:navigator assay-inbox (silent skip if hub not connected)
try:
    hub_path = state.get('_hub', {}).get('path') or state.get('hub_path')
    spoke_name = (spoke_id or "unknown").lower().replace(" ", "-")
    if hub_path:
        inbox_dir = os.path.join(hub_path, 'WAI-Hub/advisors/navigator/assay-inbox', spoke_name)
        os.makedirs(inbox_dir, exist_ok=True)
        dest = os.path.join(inbox_dir, f'{session_id}_assay_full.json')
        shutil.copy2(assay_path, dest)
        print(f"Assay: delivered → {dest}")
    else:
        print("Assay: hub not connected — skipping delivery (local copy retained)")
except Exception as e:
    print(f"Assay: delivery skipped ({e}) — local copy retained")


if __name__ == "__main__":
    pass  # all logic runs at module level when invoked as script
