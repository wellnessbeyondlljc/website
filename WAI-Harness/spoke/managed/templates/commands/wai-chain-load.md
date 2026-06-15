# WAI Chain Load — Minimal Context Protocol

**ID:** wai-chain-load
**Type:** context-load-protocol
**Lifecycle:** stable
**Safety Level:** 10

---

## Purpose

When the work queue auto-chain mode transitions to the next lug, load only the minimal context needed to execute that lug. This is the **chain mode load protocol** — do NOT run full wakeup (`/wai`).

**Target:** ~7–12k tokens (vs ~46k for full wakeup)

---

## Protocol

### Step 1: Load WAI-State Identity Subset

Read `WAI-Spoke/WAI-State.json`. Extract these 7 fields only:

```python
import json

with open('WAI-Spoke/WAI-State.json', 'r') as f:
    s = json.load(f)

identity = {
    # From wheel section
    "project":        s["wheel"]["name"],
    "version":        s["wheel"]["version"],
    "fw_version":     s["wheel"]["framework_version"],
    "node_type":      s["wheel"]["node_type"],
    # From _session_state section
    "session_count":  s["_session_state"]["session_count"],
    "active_session": s["_session_state"]["current_session"],
    "track_path":     s["_session_state"]["track_path"],
}
```

**Do NOT read these WAI-State sections:** `_work_queue`, `_advisor_state`, `analytics`, `model_log`, `characteristics`, `_project_foundation` (body), `feature_toggles`, `spokes`, `context`, `ai_rules`, `ai_context`, `environments`, `meta`.

### Step 2: Read Target Lug

Read the target lug JSON in full. The lug ID is provided by the chain invocation.

Path pattern: `WAI-Spoke/lugs/bytype/{type}/{status}/{lug_id}.json`

Read the full lug — PEV, acceptance criteria, and file targets are needed to execute.

### Step 3: Read Last 2 Track Turns

```python
import json

track_path = identity["track_path"]  # from Step 1

with open(track_path, 'r') as f:
    lines = [l for l in f.readlines() if l.strip()]

last_2 = [json.loads(l) for l in lines[-2:]]
```

Read only the last 2 entries. Do not load full session history.

### Step 4: Begin Work

With these three reads complete, begin work on the lug directly:
- Identity context establishes project + session
- Lug provides full execution spec (PEV, steps, acceptance criteria)
- Last 2 turns provide immediate continuity

No further reads are required before starting execution.

---

## Exclusions

**Do NOT run in chain mode:**
- `session-start.sh`
- `tools/score_backlog.py`
- `tools/spoke_expediter.py`
- Full wakeup briefing (`/wai`)
- Hub teaching check
- Wakeup brief (`WAI-Spoke/wakeup-brief.json`)
- Skills registry or capability registry scans

---

## Token Estimate

| Source | Tokens |
|---|---|
| WAI-State identity subset (7 fields) | ~1k |
| Target lug (full) | ~2–5k |
| Last 2 track turns | ~2k |
| This skill | ~2k |
| **Total** | **~7–12k** |

**Contrast:** Full wakeup (`/wai`) loads ~46k tokens. Chain mode saves ~34–39k tokens per chained item.

---

## Exit

After completing the lug, run `/wai-closeout` normally. The closeout skill handles UAT capture, chain proposal, and commit regardless of how the session was loaded.
