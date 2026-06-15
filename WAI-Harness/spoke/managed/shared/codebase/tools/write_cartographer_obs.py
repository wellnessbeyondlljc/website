#!/usr/bin/env python3
# tools/write_cartographer_obs.py — record a Cartographer session observation
#
# Usage: python3 tools/write_cartographer_obs.py <track_path>
#
# Reads the session track.jsonl at <track_path>, derives model/work-type/rework
# metrics, and writes a structured observation to WAI-Spoke/cartographer/observations/.
# Run from the project root.

import sys

if len(sys.argv) < 2:
    print("Usage: write_cartographer_obs.py <track_path>", file=sys.stderr)
    sys.exit(1)

import json, re, os, datetime, glob

track_path = sys.argv[1]
observations_dir = "WAI-Spoke/cartographer/observations"
os.makedirs(observations_dir, exist_ok=True)

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
    print("Cartographer: no track found — skipping observation")
    sys.exit(0)

# Count rework events (user turns containing rework phrases)
REWORK_PHRASES = ["try again", "that is wrong", "that's wrong", "redo", "not what i asked",
                  "start over", "rewrite", "fix that", "that's not right", "wrong answer"]
rework_count = sum(
    1 for ev in events
    if ev.get("role") == "user"
    and any(p in str(ev.get("content", "") or ev.get("message", "") or "").lower()
            for p in REWORK_PHRASES)
)

# Count lug status transitions
lug_reversions = sum(
    1 for ev in events
    if ev.get("event") == "lug_status_change"
    and ev.get("from_status") == "in_progress"
    and ev.get("to_status") == "open"
)
lug_progression = sum(
    1 for ev in events
    if ev.get("event") == "lug_status_change"
    and ev.get("to_status") == "completed"
)

# Session metadata from WAI-State
try:
    state = json.load(open("WAI-Spoke/WAI-State.json"))
except Exception:
    state = {}

spoke_id = state.get("spoke_id", "unknown")
sess = state.get("_session_state", {})
session_vibe = sess.get("vibe") or None
session_id = sess.get("session_id") or "unknown"

# Model ID — check session state first, then scan track events
model_id = sess.get("model_id") or "unknown"
if model_id == "unknown":
    for ev in events:
        if ev.get("model"):
            model_id = ev["model"]
            break

# Provider — derive from model_id
provider = (
    "anthropic" if "claude" in model_id.lower() else
    "openai"    if "gpt" in model_id.lower() or "o1" in model_id.lower() else
    "gemini"    if "gemini" in model_id.lower() else
    "z_ai"      if "glm" in model_id.lower() or "z.ai" in model_id.lower() or "zai" in model_id.lower() else
    "together"  if "/" in model_id else
    "unknown"
)

# Dominant work type — priority-ordered rules from active lugs + vibe
active_lugs = []
for path in glob.glob("WAI-Spoke/lugs/bytype/*/in_progress/*.json"):
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

# Build and write observation record
obs = {
    "session_id": session_id,
    "spoke_id": spoke_id,
    "date": datetime.date.today().isoformat(),
    "model_id": model_id,
    "provider": provider,
    "dominant_work_type": dominant_work_type,
    "work_type_distribution": {},
    "task_complexity_mode": None,
    "session_vibe": session_vibe,
    "turn_count": turn_count,
    "tokens_in": None,
    "tokens_out": None,
    "rework_event_count": rework_count,
    "lug_reversions": lug_reversions,
    "lug_progression": lug_progression,
    "quality_score": None,
    "rework_rate": None,
    "scoring_method": None,
    "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
}

out_path = f"{observations_dir}/session-{session_id}-obs.json"
with open(out_path, "w") as f:
    json.dump(obs, f, indent=2)
print(f"Cartographer: observation written → {out_path}")
print(f"  model={model_id} | work={dominant_work_type} | rework={rework_count} | progressions={lug_progression}")


if __name__ == "__main__":
    pass  # all logic runs at module level when invoked as script
