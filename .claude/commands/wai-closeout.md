### 2. Intent Ceremony Gate

Read `WAI-Spoke/runtime/session-intent.json` if it exists. Map `intent` to ceremony level:

| intent | ceremony |
|--------|----------|
| `closeout` | Minimal |
| `implement` / `refinement` / `teachings` / `explore` | Standard |
| `full` | Full |
| absent / unknown | Standard |

Surface: `[Closeout] Intent at session start: {intent} → ceremony: {level}`

**Minimal** (intent=`closeout`): skip steps 8 (Dogfooding), 9b (Teaching Generation), 9c (Hub Signal Bulletin). Proceed: 3 → 4–5 → 5d → 6 → 7 → 10 → 11.

**Standard** / **Full**: run all steps.

**If intent=`implement`:** after lug archival (step 5), verify at least one lug transitioned `in_progress → completed` this session. If none: surface `Intent was implement but no lugs completed — expected?` and wait for acknowledgment before continuing.

---

### 3. Incomplete Work Capture

Document unfinished work with enough detail to resume: status, what's done, what remains, blockers, files, continuation instructions. Store in session-summary `incomplete_work` AND `_session_state.next_session_recommendation`.

If a session track exists, also read `open` items from the last 3 track points.

### 4–5. Run Closeout Script

```bash
tools/closeout.sh --modified-by {model_id} --track-path {current_track_path}
```

Handles automatically: version bump, `session_count++`, `last_closeout`/`last_modified_at`/`last_modified_by`, lug archival (`in_progress` → `completed` for status==completed lugs), `WAI-LugIndex.jsonl` regen, backlog scoring + `_work_queue` update.

Add `--dry-run` to preview without writing.

Review the printed summary, then complete the remaining AI-only fields:

**AI completes in WAI-State.json:**
- `_session_state.next_session_recommendation` = what the next session should focus on
- `_session_state.track_path` = current session track path (if not passed via `--track-path`)

**Capability check:** `test -d WAI-Spoke/lugs/bytype && echo BYTYPE_OK || echo FLAT_LUG` — if FLAT_LUG, skip 5b and 5c entirely.

### 5b. Adoption Marker Sync

For each implementation lug with `status = "implemented"`: check `_migration_state.adoption_markers` in extended state. If `adopted = false`, update to `true` with timestamp.

### 5c. Hub Routing (FRAMEWORK / SIGNAL / SPOKE lugs only)

Script handles LOCAL archival. For non-LOCAL lugs, AI routes manually:
- **FRAMEWORK** → completed + hub teachings (Step 9b)
- **SIGNAL** → `bytype/signal/delivered/` + hub bulletin (Step 9c)
- **SPOKE/{id}** → copy to hub incoming + complete locally

Move delivered signals from `undelivered/` to `delivered/`.

### 5d. Changelog Entries

For each resolved lug, append to `WAI-Spoke/runtime/spoke-changelog.jsonl`. See `wai-closeout-reference.md` for changelog entry format. Framework-internal changes go in CHANGELOG.md, not spoke-changelog.

### 6. Finalize Session Track

Write a final track point as the **terminal entry** — this is the marker wakeup Step 3b uses to detect a clean session. The entry MUST include both `event: "closeout"` and `completed: true`:

```json
{"event": "closeout", "completed": true, "session_id": "{session_id}", "ts": "{ISO-8601}", "phase": "review", "session_number": N}
```

Do NOT delete the track file — it's the permanent session record. A session without this terminal entry will show as INTERRUPTED on next wakeup.

### 6b. Cartographer Observation

After the session track is finalized, record a structured usage observation so Navigator can build local model performance history.

```python
import json, re, os, datetime, glob

track_path = "{current_track_path}"  # same value passed to closeout.sh
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
                    events.append(json.loads(line))
                except Exception:
                    pass
except FileNotFoundError:
    print("Cartographer: no track found — skipping observation")
    exit(0)

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
```

### 6c. Assay Write + Hub Delivery

After the Cartographer observation, write `assay_full.json` for this session and deliver it to hub:navigator.
PII-free: captures only model IDs, provider names, tool names, work_type labels, lug IDs — never message content.

```python
import json, os, datetime, shutil

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
```

### 7. Documentation Updates

Update `CHANGELOG.md` if applicable. Generate descriptive commit message.

### 7b. Docs Sync (When Protocol Changes)

**Trigger:** Session modified skills, protocol files, architecture, or lug schema.

1. Update README.md version string and skill list if changed
2. `framework/docs/llms-full.md` is regenerated automatically by `tools/closeout.sh` Step 6 — verify it updated (check timestamp or line count changed)
3. If no protocol changes: note "Skip 7b: no protocol changes"

### 8. Lug Dogfooding

Validate lugs created/modified this session (excluding session-summary and autosave). For each lug, check:

- PEV fields present? `perceive` points to real files? `execute` has concrete steps? `verify` defines done state? Self-contained?
- **verify testable?** Heuristic: `verify` length > 50 chars AND contains at least one action verb (`run`, `check`, `confirm`, `open`, `call`, `assert`, `create`). If fails: flag `non-testable verify`.
- **verify actually run?** Scan session track (`WAI-Spoke/sessions/{session_id}/track.jsonl`) for a `verification` event that references this lug id. If absent: flag `verify steps not recorded as run`.

For each flagged lug, surface:
```
{lug_id}: {flag} — [Y]es, I ran it / [S]kip / [A]dd verify steps now
```
- `Y` — record a `{"event": "verification", "lug_id": "{id}", "ts": "..."}` entry in track, continue.
- `S` — continue (flag noted in session summary).
- `A` — open inline edit of the lug's `verify` field before closing out.

Present plan, wait for approval, fix gaps. Skip if no actionable lugs.

### 9. Outgoing Delivery

Check `WAI-Spoke/lugs/outgoing/` for queued deliveries. If hub connected: copy to hub incoming. If hub unreachable: note in next_session_recommendation.

### 9b. Teaching Generation + Hub Publish

**If no teaching-worthy changes:** Skip. Note "No new teachings."

**If changes exist:** Group into families, determine version bump, generate to `teachings/`. Hard gate: each teaching MUST include Prerequisites block, Batch Sequence block, and `safe_to_auto_adopt` flag (default `true`, `false` only for breaking changes). Enforce single-current rule. If hub connected: publish + archive + rewrite index.

**Before promoting to spoke/codebase/templates/:** Run `test-bench/teaching-verify.sh teachings/<file>.teaching` against each new teaching. PASS required before distribution.

**Scope boundary:** Hub publish = file writes to `{hub_path}/` via the filesystem only. Never run `git add`, `git commit`, or any git command inside `{hub_path}`. Hub commits are the hub's own responsibility at its next session.

See `wai-closeout-reference.md` for teaching format details and hub publish layout.

### 9b-2. Spoke Telemetry Rollup

Run spoke-telemetry-closeout skill (templates/commands/spoke-telemetry-closeout.md):
1. Read session track.jsonl → extract model_telemetry entries
2. Aggregate into model_usage[] by model_id
3. Compute dominant_model, work_type_distribution, peak_hour_utc
4. Write rollup to `WAI-Spoke/telemetry/session-{session_id}-rollup.json`
5. Deliver rollup to hub Assessor inbox: `{hub_path}/WAI-Hub/advisors/assessor/inbox/{session_id}-rollup.json`
   If hub unreachable: note in session record, do not block.

Report: "Telemetry rollup written for session {session_id}. Delivered to Assessor."

### 9c. Hub Signal Bulletin (Target-Routed)

Deliver signals with two-tier routing — **destination is determined at delivery time, not triage time**.

**Signals to deliver:** all files in `bytype/signal/undelivered/`, plus any lug with `routed_to=SIGNAL` or `impact >= 8`.

**Resolve destination — use `routed_to` first, fall back to `target` if `routed_to` is absent:**

| `routed_to` | `target` / `destination` (fallback) | Destination |
|---|---|---|
| `FRAMEWORK` | `"framework"` | `{hub_path}/WAI-Hub/signals/incoming/framework/` |
| `HUB` | `"hub"` | `{hub_path}/WAI-Hub/signals/incoming/hub/` |
| `SIGNAL` or absent | `"all-spokes"` / `"spokes"` / `"spoke"` / absent | `{hub_path}/WAI-Hub/signals/incoming/spokes/` |
| `SPOKE/{id}` | `"spokes/{id}"` | `{hub_path}/WAI-Hub/signals/by-target/spokes/` |
| any | `destination="hub-kb"` | `{hub_path}/WAI-Spoke/lugs/incoming/` (Ozi routes to Librarian) |

**Hub-KB destination (Historian Bucket 3):** If a signal lug has `destination: "hub-kb"`, copy it to `{hub_path}/WAI-Spoke/lugs/incoming/` regardless of `routed_to`. Ozi at the hub routes `destination=hub-kb` lugs to the Librarian advisor on intake. Requires `qualifiers` block — if absent, add `"_routing_note": "qualifiers missing — held for manual review"`.

If neither `routed_to` nor `target` is set: deliver to `incoming/spokes/` and add `"_routing_note": "target missing — defaulted to spokes"` to the delivered file.

**For signals routed to `incoming/framework/`:**

Apply the quality gate:
- `impact >= 8` AND
- `signal` or `rationale` field is non-empty (has a body — not title-only) AND
- Pattern is cross-spoke-generalizable (not stack-specific, not project-specific)

If all pass → **direct-promote**: write a `.md.teaching` file to `{hub_path}/teachings_repo/framework/current/{signal_id}.md.teaching` using this template:

```
# Teaching: {title} v1

**Family:** framework
**Version:** 1.0
**Created:** {YYYY-MM-DD}
**Impact:** {impact}
**Source Session:** {session_id}
**safe_to_auto_adopt:** true

---

## Prerequisites
None — standalone.

## Batch Sequence
**Batch:** {signal_id}-v1 | **Apply order:** 1 of 1 | **Parallel safe:** yes

---

## What This Teaching Does

{title}

{signal/rationale body}

---

## Post-Completion
Move this file to `WAI-Spoke/seed/ingest/processed/`.
```

If any gate fails → **queue for curation**: write JSON to `{hub_path}/WAI-Hub/signals/incoming/framework/{signal_id}.json`.

**For all other destinations:** write the signal JSON as-is. Skip (do not overwrite) if the file already exists — dedup by filename.

Move delivered signals: `bytype/signal/undelivered/` → `bytype/signal/delivered/`.

Report: "Delivered N signals — M direct-promoted to teachings_repo, K to incoming/framework/, J to incoming/hub/, L to incoming/spokes/, P to by-target/spokes/. Q already present (skipped)."

**Signal lifecycle:** arrive → quality-gate → direct-promote OR triage → incorporate → teach → clear. Signals must not accumulate.

### 9d. Spoke Registry Update

Extract from WAI-State.json: `spoke_id`, `name`, `version`, `status`, `one_liner`, `session_count`, `last_closeout`. Write to `{hub_path}/WAI-Hub/registry/incoming/{spoke_id}.json` with `reported_at`. If hub unreachable: note, don't block.

### 10. Skill Sync

Sync canonical skill source to installed copy so the next session runs current skills:

```bash
\cp templates/commands/*.md .claude/commands/
```

Verify: `diff templates/commands/wai.md .claude/commands/wai.md && diff templates/commands/wai-full.md .claude/commands/wai-full.md` — no output = clean.

### 10c. Work Queue Update

Update `_work_queue` in `WAI-State.json`:
1. Mark completed lugs in `_work_queue.items` as `status: "done"` (match by id against items moved to `completed/` this session)
2. Run `python3 tools/score_backlog.py --update-state` to refresh readiness and queue_state counts
3. If `auto_chain` was set this session (user chose [A] at Step 9) and `ready_count > 0`: run this script:

```python
import json, datetime, os

# Load work queue
state = json.load(open('WAI-Spoke/WAI-State.json'))
wq = state.get('_work_queue', {})
items = wq.get('items', [])
completed_this_session = []  # fill from lugs moved to completed/ this session

# Find next ready item (exclude just-completed)
next_item = next(
    (item for item in sorted(items, key=lambda x: x.get('roi', 0), reverse=True)
     if item.get('readiness') == 'ready' and item.get('id') not in completed_this_session),
    None
)

# Write UAT track entry for the completed lug
session_id = state.get('_session_state', {}).get('current_session_id', 'unknown')
track_path = f'WAI-Spoke/sessions/{session_id}/track.jsonl'
if os.path.exists(track_path) and completed_this_session:
    uat_entry = {
        'turn_type': 'uat',
        'lug_id': completed_this_session[0],
        'acceptance': 'accepted',
        'notes': 'Auto-chain mode: lug completed, queuing next item',
        'auto_chained': True,
        'next_item_id': next_item.get('id') if next_item else None,
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    with open(track_path, 'a') as f:
        f.write(json.dumps(uat_entry) + '\n')
    print(f'UAT track entry written for {completed_this_session[0]}')

# Write chain_target_lug to wakeup-brief.json
brief_path = 'WAI-Spoke/wakeup-brief.json'
if os.path.exists(brief_path):
    brief = json.load(open(brief_path))
    brief['chain_target_lug'] = next_item if next_item else None
    with open(brief_path, 'w') as f:
        json.dump(brief, f, indent=2)
    if next_item:
        print(f'Auto-chain: next session will load {next_item["id"]} (ROI {next_item.get("roi")})')
    else:
        print('Auto-chain: queue empty -- chain_target_lug set to null')
```

**UAT Track Schema:**
```json
{
  "turn_type": "uat",
  "lug_id": "string -- the completed lug id",
  "acceptance": "accepted|deferred|rejected",
  "notes": "string -- brief description of what was accepted",
  "auto_chained": "boolean -- true if auto_chain mode was active",
  "next_item_id": "string|null -- the id of the next queued lug",
  "timestamp": "ISO-8601"
}
```

If no next ready item after completion: `chain_target_lug` is set to `null` — no error. Offer `[R]eview refinements` or exit to normal closeout.

### 10d. Session Status Update

Before committing, mark the session clean in WAI-State:

```bash
python3 -c "
import json, datetime, os
state_path = 'WAI-Spoke/WAI-State.json'
ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
with open(state_path, 'r') as f:
    state = json.load(f)
if '_session_status' not in state:
    state['_session_status'] = {}
state['_session_status']['status'] = 'clean'
state['_session_status']['clean_at'] = ts
state['_session_status']['interrupted_at'] = state['_session_status'].get('interrupted_at')
state['_session_status']['interrupted_session'] = None
with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)
print(f'_session_status.status = clean @ {ts}')
"
```

### 11. Completion Banner + Git Commit + Push

Display the banner **before** committing, then auto-proceed after 10s unless user cancels:

```
-- CLOSEOUT Session-{N} [{track_name}] {timestamp}
|  Accomplished: {bullets}  |  Incomplete: {list or "none"}
|  Version: v{old} -> v{new}  |  Context: {X}%  |  Signals: {N}
|  Ceremony: Full|Standard|Essential|Minimal  |  Commits: {N} files
-- Commit on next tool call — type cancel to abort.
```

Wait 10s. If user types `cancel`, `stop`, `abort`, `no`, or `wait` (case-insensitive): abort. On timeout or any other input (including questions): proceed. If user asks a question: answer it inline, then continue — do **not** re-present the banner.

**Pre-commit: concurrent session check**

```bash
# Fetch remote state (no merge)
git fetch origin 2>/dev/null || true

# Check if remote is ahead
REMOTE_AHEAD=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo 0)
if [[ "$REMOTE_AHEAD" -gt 0 ]]; then
    echo "Remote has $REMOTE_AHEAD new commit(s) — pulling before commit to avoid conflict..."
    git pull --rebase origin main
    echo "Rebase complete. Review any conflicts before proceeding."
fi

# Check if WAI-State.json was externally modified since session start
# (another concurrent session already closed out and updated it)
STATE_SHA_NOW=$(git show HEAD:WAI-Spoke/WAI-State.json 2>/dev/null | md5sum | cut -c1-8 || echo "new")
STATE_SHA_SESSION=$(git show "$(cat WAI-Spoke/runtime/session-guard.json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_start_sha","HEAD"))' 2>/dev/null || echo HEAD)":WAI-Spoke/WAI-State.json 2>/dev/null | md5sum | cut -c1-8 || echo "unknown")
if [[ "$STATE_SHA_NOW" != "$STATE_SHA_SESSION" && "$STATE_SHA_SESSION" != "unknown" ]]; then
    echo "WAI-State.json was modified by another session since this session started."
    echo "Review the diff before proceeding:"
    git diff HEAD WAI-Spoke/WAI-State.json 2>/dev/null || true
fi
```

**Classify working tree changes:**

```bash
git status --short
```

- **In-scope:** files explicitly touched this session (from track, lug target_files, or known session artifacts like `WAI-State.json`, session track, runtime logs)
- **Out-of-scope:** everything else (hook event logs, advisor outputs, files from concurrent sessions)

If out-of-scope files exist, append to the commit message: `| also: {file list or count} (hook/advisor artifacts)`

**Pre-commit lug verify gate:**

Check for lugs moved to `completed/` this session that have no `verify` field:

```bash
python3 -c "
import json, glob, os, sys
no_verify = []
for p in glob.glob('WAI-Spoke/lugs/bytype/*/completed/*.json'):
    try:
        lug = json.load(open(p))
        if not lug.get('verify'):
            no_verify.append(lug.get('id', os.path.basename(p)))
    except Exception:
        pass
if no_verify:
    print(f'WARN:{len(no_verify)}:' + ','.join(no_verify))
"
```

If output starts with `WARN:`: append `| ⚠ {N} lug(s) completed without verify steps` to the commit message.

**Pre-commit public sync check:**

```bash
python3 tools/check_public_sync.py
```

If output is not `OK`: run `python3 tools/check_public_sync.py --fix` and include the synced files in the commit. Prevents `shared/codebase/tools/` from drifting behind `tools/`.

```bash
git add -A
git commit -m "WAI Session [N]: [accomplishments] | [version] | also: {out-of-scope summary if any}"
git push origin main
```

**If push still fails after rebase:** merge conflict in WAI-State.json or another file. Surface the conflict, resolve manually (keep both sessions' `session_count` increments by taking the higher value), then push. Do NOT force-push.

**Critical:** `WAI-Spoke/WAI-State.json` listed explicitly first to guarantee staging. If Minimal ceremony, include `(minimal closeout — full deferred)` in message.

### 11b. Generate Ozi Brief

After commit, generate the pre-computed Ozi snapshot for the next wakeup:

```bash
python3 tools/generate_ozi_brief.py
```

### 11c. Generate Wakeup Brief

Generate the wakeup brief so the next session starts on fast path:

```bash
python3 tools/generate_wakeup_brief.py
```

### 11c. Generate Octo Brief (Hub Projects Only)

**Skip if not a hub project.** Detect: `wheel.node_type == "hub"` in WAI-State.json OR `WAI-Hub/` directory exists.

After Ozi brief, generate `WAI-Hub/octo-brief.json` — a pre-computed fleet snapshot.

```bash
python3 -c "
import json, datetime, os, glob

if not os.path.isdir('WAI-Hub'):
    print('Not a hub project — skipping Octo brief.')
    exit(0)

fleet = {'green': 0, 'yellow': 0, 'red': 0, 'red_spoke_names': [], 'yellow_spoke_names': []}
gs_path = 'WAI-Hub/advisors/gardener/scan_state.json'
if os.path.isfile(gs_path):
    gs = json.load(open(gs_path))
    for spoke in gs.get('spokes', {}).values():
        health = spoke.get('health', 'unknown')
        name = spoke.get('name', spoke.get('id', ''))
        if health == 'green': fleet['green'] += 1
        elif health == 'yellow':
            fleet['yellow'] += 1
            fleet['yellow_spoke_names'].append(name)
        else:
            fleet['red'] += 1
            fleet['red_spoke_names'].append(name)

priority = []
sp_path = 'WAI-Hub/advisors/spinner/spoke_spinner.json'
if os.path.isfile(sp_path):
    sp = json.load(open(sp_path))
    ranked = sorted(sp.get('spokes', {}).items(), key=lambda x: x[1].get('urgency', 0), reverse=True)[:5]
    priority = [s[0] for s in ranked]

adv = {'gardener_last_run_at': None, 'spinner_last_scored_at': None, 'cartographer_last_scan_at': None}
if os.path.isfile(gs_path):
    adv['gardener_last_run_at'] = json.load(open(gs_path)).get('last_run_at')
if os.path.isfile(sp_path):
    adv['spinner_last_scored_at'] = json.load(open(sp_path)).get('last_scored_at')
cs_path = 'WAI-Hub/advisors/cartographer/scan_state.json'
if os.path.isfile(cs_path):
    adv['cartologist_last_scan_at'] = json.load(open(cs_path)).get('last_scan_at')

sig = {'undelivered_by_target': {}, 'incoming_count': 0}
for f in glob.glob('WAI-Hub/signals/by-target/*/*.json'):
    target = os.path.basename(os.path.dirname(f))
    sig['undelivered_by_target'][target] = sig['undelivered_by_target'].get(target, 0) + 1
sig['incoming_count'] = len(glob.glob('WAI-Hub/signals/incoming/*.json'))

brief = {
    'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'fleet_snapshot': fleet,
    'priority_order': priority,
    'advisor_state': adv,
    'signal_pipeline': sig,
    'next_triumvirate_run': None
}
os.makedirs('WAI-Hub', exist_ok=True)
with open('WAI-Hub/octo-brief.json', 'w') as f:
    json.dump(brief, f, indent=2)
print('Octo brief written: WAI-Hub/octo-brief.json')
"
```

### 12. Verification

Verify: `git status` (clean), `git log --oneline -1`, `git tag -l | tail -1` (if production).

Print: `-- Session saved. Next wakeup loads exactly where we left off.`

If Minimal: add `Context was critical — full ceremony deferred. Run /wai-closeout next session.`

If the session was launched via a GUI tool (VS Code, Cursor) or directly without `wai-enter.sh`, add:
`If you didn't use wai-enter.sh to launch: run ./wai-exit.sh now to keep the wakeup brief fresh. Without it, non-hook tools (codex, gemini) will read stale queue/signal data next session.`

### 13. Release Tag (Production Releases Only)

Skip if not production. Tag `v$VERSION`, push tag. If tag exists: stop and report conflict.

### 14. Verification

`git status` (clean), `git log --oneline -1`, `git tag -l | tail -1` (if production).

---

## Automated Closeout Protocol

Applies to Tender and any automated agent that performs work on a spoke without a human in the loop. The ceremony is minimal but must produce the same measurable artifacts as a human session so Surveyor and Gardener see valid events.

### Mandatory (automated runs must always do these)

| Step | What | How |
|---|---|---|
| State update | `WAI-State._session_state.last_closeout` = ISO 8601 timestamp | Python update to WAI-State.json |
| State update | `WAI-State.session_count += 1` | Same write |
| State update | `WAI-State.wheel.last_updated` = same timestamp (if key exists) | Same write |
| Track | Create `WAI-Spoke/sessions/session-{date}-tender-{HHmm}/track.jsonl` | Single-entry JSONL |
| Commit | `git add WAI-Spoke/WAI-State.json WAI-Spoke/sessions/{dir}/` then commit | Message: `chore: tender automated closeout {ts} — s={n} t={n} l={n}` |

### Minimal track entry schema

```json
{
  "ts": "2026-04-16T03:00:00Z",
  "session": "session-20260416-tender-0300",
  "type": "automated-tender",
  "summary": "Tender pass: signals=2, teachings=1, lugs=0",
  "signals_processed": 2,
  "teachings_adopted": 1,
  "lugs_executed": 0
}
```

### Optional (skip in automated runs unless the pass specifically produced them)

- Signal extraction — only if Tender created new signals
- Teaching generation — only if Tender completed a lug that requires one
- Version bump — automated runs do not bump version
- Full session summary — omit; track entry is sufficient

### What automated closeout must NOT do

- Read or modify any file outside the spoke's `WAI-Spoke/` directory and the spoke's own git index
- Include unintended files in git commit (only `WAI-State.json` + session track directory)
- Skip the ceremony when no work was done — state + track must always be written so Surveyor sees the run

---

## Success Criteria

- Quality gates pass (if production)
- Autosave lugs reconciled into session-summary
- Signals extracted (impact >= 8)
- Incomplete work documented
- Version incremented, state updated
- Lug status synced, index regenerated
- Session track finalized
- Lugs dogfooded (if applicable)
- Teachings generated (if applicable)
- Committed and pushed
- Release tag applied (if production)
- **All target_files for completed lugs were verified to exist on disk**

---

*Closeout = Save game. Next agent continues the adventure.*
