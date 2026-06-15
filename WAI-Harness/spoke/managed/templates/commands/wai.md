# WAI Wakeup Protocol
> Fast path: load `wai-slim.md` first. Load this file only when deep protocol is needed.

Execute wakeup to initialize the spoke.

---

## Check: Is Session Data Fresh?

Look for `<wai-session-init>` in context and check if it contains `Wakeup brief: FRESH`.

---

## FAST PATH — 0 tool calls (FRESH brief)

Pre-conditions met: hook pre-computed all data, track entry already written by session-start.sh.

**DO NOT make any tool calls.** Display the briefing immediately.

**Steps:**

**0. Intent check.** Scan `<wai-session-init>` CONTEXT HEALTH for an `Intent:` line.
- If found: extract `SESSION_INTENT` and `SESSION_INTENT_LABEL`. After Step 2 banner, jump to **Step 2b** (intent router). Skip Steps 3 and 4.
  - If `SESSION_INTENT = savepoint`: check `WAI-Spoke/runtime/session-intent.json` for `savepoint_resumed = true`. If true, set `SAVEPOINT_ALREADY_CONFIRMED = true` (no prompt needed — wai-enter.sh already captured the choice).
- If absent: proceed normally through Steps 1–4.

**1. Interrupted session check.** If `Prev session: INTERRUPTED` in session-init CONTEXT HEALTH: note it in the banner as `⚠ Prev session interrupted — recovery prompt shown pre-launch`. No action needed — recovery was handled by wai-enter.sh before launch.

**2. Display banner** using session-init sections:

```
┌─ WAI WAKEUP Session-{N} [{session_name}] {today_date}
│  Project: {name} v{version}               ← STATIC DATA
│  Active: {epics_open} open, {epics_ip} ip | {other_open} other | {signals} signals
│  Queue: {ready} ready | {refinement} refinement     ← Expediter line
│  {If _savepoint.status == "pending": ⚑ Savepoint: [lug_id] | Silo: [silo_label] ({initiative_id}) | Done: [work_done] | Next: [resume_note]}
│  {If savepoint.focus_directive: Focus lock: [focus_directive]}
│  Intent: {intent} — {intent_label}   ← If intent set; otherwise: Vibe: none  |  Context: unknown — run /context
│  {If TEACHINGS New > 0: ⚑ Teachings: N pending (Path A/B) — adopt before work queue}
│  {If incoming_lugs_pending > 0: ⚑ Incoming: N lugs unprocessed — triage before work queue}
│  {If HUB SIGNALS > 0: Hub signals: N framework}
│  {If recommendations valid: Navigator: N profiles current | If stale or null: ⚠ Navigator: recommendations stale}
│  {If TOOL ADVISOR audit due: ⚠ Tool audit due}
│  {If Hook drift in CONTEXT HEALTH: ⚠ Hook drift: N hooks stale (oldest: Xd) — sync recommended}
│  {If context feeds stale: Context feeds: N stale}
│  {If HISTORIAN ADVICE present: Historian: {first bullet}}
│  {Active feedback: top-3 from MEMORY.md feedback entries — see Step 3b}
│  Next: {first item from NEXT ACTIONS}
└─ Ready to work.
```

**0.5 — Priority Gate (mandatory, runs before intent router and savepoint intercept):**

If a hub base is reachable, OR `TEACH_NEW > 0`, OR `Incoming: N lug(s) pending triage` — execute A → B → C silently, **in that order**, before any other step. Do not present a savepoint prompt or work queue until all complete.

**Order is load-bearing: base adoption (A) is a HARD PREREQUISITE for teaching/patch adoption (B).** A spoke that is behind on its base MUST level up first; patches and teachings are deltas *against the current base* and do not apply to an old base. "Absorb teachings" therefore always forces base adoption first.

**A — Harness base adoption (FIRST — hard gate):**

Compare this spoke's `WAI-State.json._harness.base_version` to the hub's `teachings_repo/spoke/base/index.json` `base_version`.

- **Behind (spoke `base_version` < hub, or `_harness` absent):** run the Base Harness Adoption Kit **once** — read `{hub}/teachings_repo/spoke/base/01-orient.md` → `06-verify.md` in order (the base folder is flat — only the current version lives there; the version is `base/index.json` `base_version`). Greenfield/brownfield branch is idempotent re-assert; emit an `adoption` bolt, set `_harness.base_version` + `base_bolt_id`. A behind spoke levels up by running the kit, **not** by adopting N stale teachings. **Do not proceed to B until base is current** — stale teachings against an old base are skipped, not applied.
- **Current:** continue to B.

One-line report: `Step 0.5A: base {version} current` (or `kit run → base {version}` if leveled up).

**B — Teaching + patch adoption** (when base is current AND TEACH_NEW > 0 or patches pending):

First apply any unadopted entries in the hub `base/teachings/index.json` in order, appending each id to `_harness.patches_adopted` (cap ≤10). **Base cutting is AUTOMATIC** — when the patch set reaches the cap, `base_cut_draft.py auto` cuts a new base version (absorbs the patches, resets the set, bumps `base_version`), so a behind spoke just levels up to the new base via Section A. No manual base-cut reminder. **Teaching lug:** Before processing any teachings, auto-create a tracking lug so closeout can associate modified files with this adoption session:

```python
import json, os, datetime, shutil
from datetime import timezone

guard_path = 'WAI-Spoke/runtime/session-guard.json'
try:
    session_id = json.load(open(guard_path)).get('session_id', 'unknown')
except Exception:
    session_id = 'unknown'

today = datetime.datetime.now(timezone.utc).strftime('%Y%m%d')
lug_id = f'teaching-adoption-{today}-{session_id}'

lug = {
    'id': lug_id,
    'type': 'task',
    'title': f'Teaching adoption: apply teachings from hub (session {session_id})',
    'status': 'in_progress',
    'va': 'grind',
    'routed_to': 'LOCAL',
    'model_fit': 'haiku',
    'created_at': datetime.datetime.now(timezone.utc).isoformat(),
    'file_targets': [],
    'done_list': [],
    'perceive': f'Hub delivered teachings to session {session_id}.',
    'execute': 'Apply each teaching per its adoption steps.',
    'verify': 'All teachings moved to processed/. file_targets lists every file modified.',
}

os.makedirs('WAI-Spoke/lugs/bytype/task/in_progress', exist_ok=True)
TEACHING_LUG_PATH = f'WAI-Spoke/lugs/bytype/task/in_progress/{lug_id}.json'
# Idempotent: skip if already created (re-run scenario)
if not os.path.exists(TEACHING_LUG_PATH):
    with open(TEACHING_LUG_PATH, 'w') as f:
        json.dump(lug, f, indent=2)
    print(f'[teaching-lug] Created tracking lug: {lug_id}')
else:
    lug = json.load(open(TEACHING_LUG_PATH))
    print(f'[teaching-lug] Resuming existing tracking lug: {lug_id}')
```

Store `TEACHING_LUG_PATH` and `lug_id` for use in subsequent steps.

Then, for each unadopted teaching listed in session-init TEACHINGS:
1. Read the teaching file from the hub at `{hub_path}/teachings_repo/spoke/current/` or `cross_spoke/current/` (or `framework/current/` if not found in the typed dirs — legacy fallback).
2. Check `safe_to_auto_adopt`:
   - **`true` → silent apply:** Read `## Adoption Steps`. Apply changes inline (Write/Edit). Run `## Verification`. If PASS: `\cp` file to `WAI-Spoke/seed/ingest/processed/{filename}`. Write track event `{"event":"teaching_adopted","teaching":"{name}","ts":"..."}`. Update tracking lug: append `{name}` to `done_list`, append all files modified during adoption to `file_targets` (read from the teaching's `## Files Modified` section or detect via `git diff --name-only`). If FAIL: write notation lug `notation-teaching-failed-{slug}` with error; still move to processed/ (won't re-fire next session).
   - **`false` → silent defer:** Write notation lug `WAI-Spoke/lugs/bytype/notation/deferred/notation-teaching-review-{slug}-v1.json` (title + "requires manual review"). `\cp` teaching file to `WAI-Spoke/seed/ingest/processed/{filename}` (won't re-fire). Write track event `{"event":"teaching_deferred","teaching":"{name}","ts":"..."}`. The notation lug surfaces in the work queue — no session-start interruption.

Both paths move the file to `processed/` immediately so the next session doesn't re-detect.
One-line report: `Step 0.5B: N patch(es) applied, N adopted, M deferred to work queue.`

**Complete teaching lug:** After all teachings are processed, move the tracking lug to completed:

```python
import json, os, shutil, datetime
from datetime import timezone

if os.path.exists(TEACHING_LUG_PATH):
    lug = json.load(open(TEACHING_LUG_PATH))
    lug['status'] = 'completed'
    lug['completed_at'] = datetime.datetime.now(timezone.utc).isoformat()
    # Deduplicate file_targets
    lug['file_targets'] = sorted(set(lug.get('file_targets', [])))
    with open(TEACHING_LUG_PATH, 'w') as f:
        json.dump(lug, f, indent=2)
    os.makedirs('WAI-Spoke/lugs/bytype/task/completed', exist_ok=True)
    dest = TEACHING_LUG_PATH.replace('/in_progress/', '/completed/')
    shutil.move(TEACHING_LUG_PATH, dest)
    print(f'[teaching-lug] Completed: {lug_id} → {dest}')
    print(f'[teaching-lug] file_targets: {lug["file_targets"]}')
    print(f'[teaching-lug] done_list: {lug["done_list"]}')
```

**C — Incoming lug triage** (when `Incoming: N lug(s)` shown):

For each `.json` file in `WAI-Spoke/lugs/incoming/` (skip `processed/` and `completed/` subdirs):
1. Read the lug. Validate: `type`, `routed_to`, non-empty `perceive`/`execute`/`verify`.
2. Valid → `\cp` to `WAI-Spoke/lugs/bytype/{type}/open/{id}.json`. Invalid/incomplete → write notation lug describing the gap instead.
3. Move original to `WAI-Spoke/lugs/incoming/processed/{filename}`.

One-line report: `Step 0.5C: N lugs triaged to bytype/.`

**Proceed to Step 2b/2c only after 0.5 completes (A → B → C).**

**2.5 — Upgrade Report Intake (runs after 0.5C, before intent router):**

Check `WAI-Spoke/lugs/bytype/upgrade-report/open/` for any unprocessed reports:

```python
import glob
reports = glob.glob('WAI-Spoke/lugs/bytype/upgrade-report/open/*.json')
```

If any found, invoke `wai-upgrade-report-intake` for each — read Steps 1–5 of that skill inline for each report file, passing its path as `report_path`. Collect `improvement_count` and `bug_count` across all reports processed. After all reports are done, surface the count in the briefing:

```
Step 2.5: N upgrade report(s) processed → M improvement lug(s) opened
```

If `outcome=fail` on any report, also surface: `⚠ N adoption failure(s) — bug lug(s) opened`.

If no upgrade-report lugs exist in open/, skip this step silently.

---

**2b. Intent router** (skip entirely if SESSION_INTENT absent — proceed to Step 3):

| Intent | Max tools | Action |
|--------|-----------|--------|
| `savepoint` | 3 | **If `SAVEPOINT_ALREADY_CONFIRMED = true`:** skip prompt — display `⚑ Savepoint confirmed at session start — continuing {lug_id}`, then read WAI-State.json `_savepoint` object (check `status=pending`) + lug file + append track, set `_savepoint.status = "resumed"`, display `Done: {work_done} | Next: {resume_note}`. If savepoint has `focus_directive`, display it and set active initiative to `initiative_id`. **If false:** show `[C]ontinue savepoint / [F]ull wakeup?` — on C: same auto-proceed; on F: clear `_savepoint = {}`, fall through to FULL PROTOCOL. **Initiative focus lock:** if the claimed savepoint has `initiative_id` set, the resuming agent MUST stay on that initiative for the session. Any item discovered outside the active silo should be recorded as a notation lug (`type: notation, status: deferred, deferred_from_initiative: {initiative_id}`) and set aside — do not act on it. |
| `implement` | 1 | Read WAI-State.json. Display top-3 ready lugs by ROI. |
| `refinement` | 1 | Read WAI-State.json. Display needs_refinement items. |
| `teachings` | 1 | List `WAI-Spoke/seed/ingest/` teaching dir. Display pending count. |
| `explore` | — | Skip router. Proceed to Steps 3+4 normally. |
| `closeout` | 0 | Display closeout reminder. Invoke `/wai-closeout`. |
| `full` | — | If `_savepoint.status == "pending"`: clear `_savepoint = {}`. Fall through to FULL PROTOCOL. |

After routing, **do not ask for vibe**. Proceed directly to work.

**2c. Savepoint intercept** (only when `SESSION_INTENT` is absent — skip if already handled by Step 2b):

If `CONTEXT HEALTH` in session-init contains a line beginning with `Savepoint: PENDING`:
- Extract `lug_id` and `resume_note` from `Savepoint: PENDING [lug_id] — resume_note`.
- Display:

```
⚑ Savepoint detected: [lug-id]
  Done: [work_done]
  Next: [resume_note]
  [C]ontinue (load lug only ~5k tokens) / [F]ull wakeup
```

If user chooses **C**:
1. Read the savepoint lug JSON only (1 tool call) — use `lug_id` from `_savepoint` (if non-null)
2. Read last 2 track entries from current `track_path` (1 tool call)
3. Write `WAI-State.json`: set `_savepoint.status = "resumed"` (1 write)
4. Display: `Continuing [lug-id]. Context: ~5k tokens. Done: [work_done] | Next: [resume_note]`
5. Begin work — skip Steps 3 and 4 entirely

If user chooses **F**:
1. Write `WAI-State.json`: clear `_savepoint = {}`
2. Continue normally to Step 3

**3. Ask:** `Vibe? (build / fix / think / grind / ship / refine) [skip]`
**After user responds:** Write chosen vibe (or `null` if skipped) to `WAI-State.json._session_state.current_vibe`. Example: `{"event": "vibe_set", "vibe": "build", "ts": "..."}`

**3a. Session start event (activity instrumentation):** After vibe is set, emit a `session_start` activity event:

```python
import subprocess, json
from WAI_Spoke_WAI_State import wheel_id, session_id  # load from WAI-State.json

event = {
    "event_type": "session_start",
    "session_kind": "user",          # or "autonomous" for cron/gardener sessions
    "wheel_id": wheel_id,
    "session_id": session_id,
    "metadata": {"vibe": vibe}       # vibe from step 3
}
subprocess.run(["python3", "tools/emit_activity_event.py", json.dumps(event)], check=False)
# Gracefully skipped if tools/emit_activity_event.py absent or SUPABASE_REST unset.
```

**3b. Active Feedback Surface:** Scan the `MEMORY.md` already loaded in context. Find all entries of type `feedback`. Pick the top 3 by most-recently-updated or most frequently-triggered. Output one compact line:

```
Active feedback (N): [rule-1 short label] | [rule-2 short label] | [rule-3 short label]
```

This line closes the apply gap — feedback entries are loaded at wakeup AND explicitly surfaced so the agent acknowledges them before starting work. If fewer than 3 feedback entries exist, show all of them. If MEMORY.md has no feedback entries, skip this line silently.

**3b. Initiative Prompt (soft, skippable):** After vibe prompt, ask once: _"Which initiative are you advancing this session? (or skip for freeform)"_ Present up to 3 options drawn from `WAI-Spoke/initiatives/bytype/initiative/{approved,active,measuring}/*.json` — priority ordered by `focus_lock=true` first, then `impact_rank` ascending. If the user picks one, write `WAI-State.json._session_state.active_initiative_id = <slug>`. If skipped or no initiatives exist, set `active_initiative_id: null`. This choice is used at closeout (Step 5b) to group completed lugs into a bolt. If `WAI-Spoke/wakeup-brief.json` contains a `continuation_menu` field, surface those open initiatives + pending savepoints as ranked options **before** any new-initiative path — finish-before-start is the default.

**4. Work Queue Interactive Mode:** After vibe prompt, if `_work_queue.items` has `>=1` ready item, display top-3 by weighted ROI (initiative impact × lug ROI).

```python
import json, os
wai_state_path = 'WAI-Spoke/WAI-State.json'
initiatives_path = 'WAI-Spoke/initiatives/index.json'
if os.path.exists(wai_state_path):
    with open(wai_state_path, 'r') as f:
        wai_state = json.load(f)
    work_queue = wai_state.get('_work_queue', {})
    initiative_weights = work_queue.get('initiative_weights', {})

    # Build initiative label lookup from index
    initiative_labels = {}
    if os.path.exists(initiatives_path):
        with open(initiatives_path, 'r') as f:
            idx = json.load(f)
        for init in idx.get('initiatives', []):
            initiative_labels[init['id']] = init['label']

    def weighted_roi(item):
        base = item.get('roi', 0)
        init_id = item.get('initiative_id', '')
        weight = initiative_weights.get(init_id, 1.0) if isinstance(initiative_weights.get(init_id), float) else 1.0
        return base * weight

    ready_items = sorted([
        item for item in work_queue.get('items', [])
        if item.get('readiness') == 'ready' and item.get('quality_score', 10) > 3
    ], key=weighted_roi, reverse=True)
    needs_refinement_items = [
        item for item in work_queue.get('items', [])
        if item.get('readiness') == 'needs_refinement'
    ]

    if ready_items:
        print("Work Queue:")
        for i, item in enumerate(ready_items[:3]):
            init_id = item.get('initiative_id', '')
            init_label = initiative_labels.get(init_id, '')
            init_tag = f" [{init_label}]" if init_label else ""
            w_roi = round(weighted_roi(item), 2)
            print(f"  [{i+1}] {item.get('id')} (ROI {w_roi}){init_tag} — {item.get('title')}")
        print("\n[W]ork top item / [R]eview refinements / [A]uto-chain / [P]arallel dispatch / [S]kip")
    elif needs_refinement_items:
        print(f"Queue: 0 ready | {len(needs_refinement_items)} need refinement")
        print("\n[R]eview refinements / [S]kip")
    # If queue is completely empty, do nothing (silent).
```

**[W] Lug gate:** Before starting work on the selected item, confirm the lug has `perceive`, `execute`, and `verify` (or `acceptance_criteria`) sections. If `verify` is absent: surface `⚠ Lug {id} has no verify steps — [A]dd now / [S]kip gate`. Do not silently start work on an unverifiable lug.

**[P] Parallel dispatch:** Call `python3 tools/batch_planner.py --json`, present the batch plan, invoke `/wai-apply-all`. See `wai-apply-all.md` for the full dispatch orchestration.

**4b. Model Intelligence (conditional — suppressed entirely if no data):**

If `WAI-Spoke/assessor-matrix.json` exists, load it and display after the Work Queue. Render only when the top queue item has a matching recommendation.

```python
import json, os, datetime

matrix_path = "WAI-Spoke/assessor-matrix.json"
if os.path.exists(matrix_path):
    matrix = json.load(open(matrix_path))
    recs = matrix.get("recommendations", [])
    generated_at = matrix.get("generated_at")

    # Get top queue item work_type and complexity (from work queue display above)
    # work_type is derived from lug type: implementation→coding, feature→planning, bug→debugging, etc.
    # complexity defaults to 3 if not on the lug

    if recs:
        # Find matching recommendation for top item (or show general best)
        best = recs[0] if recs else None
        if best:
            rec = best.get("recommended_model", {})
            model_id  = rec.get("model_id")
            provider  = rec.get("provider")
            rationale = rec.get("rationale")
            rework    = rec.get("avg_rework_rate")
            cost_tier_val = rec.get("cost_tier") or "unknown"
            confidence_val = rec.get("confidence")

            # Stale check
            stale_warning = ""
            if generated_at:
                age_days = (datetime.datetime.utcnow() -
                            datetime.datetime.fromisoformat(generated_at.rstrip("Z"))).days
                if age_days > 30:
                    stale_warning = f"  ⚠ Matrix stale ({age_days}d) — run monitor-model-registry.md"

            lines = []
            if model_id:
                provider_str = f" ({provider})" if provider else ""
                lines.append(f"  Recommended: {model_id}{provider_str}")
            if rationale:
                lines.append(f"  Rationale: {rationale}")
            if rework is not None:
                lines.append(f"  Fleet rework rate: {rework:.0%}")
            if stale_warning:
                lines.append(stale_warning)

            # New/deprecated models (if registry delta present)
            new_models = matrix.get("new_models", [])
            deprecated  = matrix.get("deprecated", [])
            if new_models:
                lines.append(f"  New models: {', '.join(new_models)}")
            if deprecated:
                lines.append(f"  Deprecated: {', '.join(deprecated)}")

            if lines:
                print("Model Intelligence:")
                for line in lines:
                    print(line)
    # If no recommendations yet, suppress entirely (silent)
```

Suppression rules: each line renders independently. If a field is null/unavailable, skip that line. If `assessor-matrix.json` does not exist, skip this entire block silently. Never print `null`, `[]`, or `{}`.

Done. Zero tool calls.

---

## BRIEF PATH — 1 tool call (no session-init, brief exists)

Pre-conditions: No `<wai-session-init>` in context AND `WAI-Spoke/wakeup-brief.json` exists.

**Steps:**

1. Read `WAI-Spoke/wakeup-brief.json` (1 tool call). Also read `WAI-Spoke/advisors/navigator/recommendations-current.json` and `WAI-Spoke/advisors/navigator/catalog-cache.json` if present (local files, silent skip if absent). For profile selection in brief-path, default to `coding_high` (no lug-type breakdown available at this step).
2. Display banner:

```
┌─ WAI WAKEUP [brief-path] {today_date}
│  Project: v{spoke_version}
│  Open lugs: {open_lug_count} | Queue: {ready_count} ready | {needs_refinement_count} refinement
│  Context: unknown — run /context  |  Vibe: none
│  {If teachings_pending > 0: ⚑ Teachings: N pending — adopt before work queue}
│  {If incoming_lugs_pending > 0: ⚑ Incoming: N lugs unprocessed — triage before work queue}
│  {If hub_signals_pending > 0: Hub signals: N pending}
│  {If recommendations exist: Navigator: matrix {generated_at_date} ✓  (or ⚠ stale {age}h if valid_through <= now)}
│  {default_mode: Available: {best_model_id} ({profile_id}, score={score}) [{provider}] [+ N others — configure API keys to unlock]}
│  {embedded_ai_mode (top ready lug tagged ai-integration/embedding-ai/llm-feature/ai-tool): Full landscape: {provider_count} providers, {model_count} models | Best: {model_id} ({provider}) | Cost: {cost_model_id} | See recommendations-current.json}
│  Next: {next_actions[0] — first 120 chars}
└─ Ready to work. (brief-path)
```

3. Ask: `Vibe? (build / fix / think / grind / ship / refine) [skip]`

**4. Work Queue Interactive Mode:** (Same as FAST PATH Step 4, adapted for brief path)

```python
import json, os
wai_state_path = 'WAI-Spoke/WAI-State.json'
if os.path.exists(wai_state_path):
    with open(wai_state_path, 'r') as f:
        wai_state = json.load(f)
    work_queue = wai_state.get('_work_queue', {})
    ready_items = sorted([
        item for item in work_queue.get('items', [])
        if item.get('readiness') == 'ready' and item.get('quality_score', 10) > 3
    ], key=lambda x: x.get('roi', 0), reverse=True)
    needs_refinement_items = [
        item for item in work_queue.get('items', [])
        if item.get('readiness') == 'needs_refinement'
    ]

    if ready_items:
        print("Work Queue:")
        for i, item in enumerate(ready_items[:3]):
            print(f"  [{i+1}] {item.get('id')} (ROI {item.get('roi', 'N/A')}) — {item.get('title')}")
        print("\n[W]ork top item / [R]eview refinements / [A]uto-chain / [P]arallel dispatch / [S]kip")
    elif needs_refinement_items:
        print(f"Queue: 0 ready | {len(needs_refinement_items)} need refinement")
        print("\n[R]eview refinements / [S]kip")
```

Done. 1 tool call.

**If brief does not exist:** fall through to FULL PROTOCOL.
**If brief is clearly stale** (git_sha_at_generation far behind HEAD): note staleness,
proceed anyway or fall through to FULL PROTOCOL.

---

## FULL PROTOCOL (STALE brief or no session-init)

### Step 1: Load Spoke Taste

Load `WAI-Spoke/taste.spoke.yaml`. If any `entries` have `status: proposed`, surface them in the briefing and prompt for action.

```python
import yaml, os
try:
    with open('WAI-Spoke/taste.spoke.yaml', 'r') as f:
        taste_data = yaml.safe_load(f)
    proposed_nudges = [e for e in taste_data.get('entries', []) if e.get('status') == 'proposed']
    if proposed_nudges:
        print(f"Taste nudges: {len(proposed_nudges)} proposed -- [a]ccept / [r]eject / [s]kip")
    # Historian nudge output format comment
    # {id, category, statement, evidence: [session_ids where correction occurred]}
except FileNotFoundError:
    pass # No taste.spoke.yaml yet, or it's empty/malformed.
```

### Step 1b: Qualifiers Check (silent if set)

```python
import json, os
state = json.load(open('WAI-Spoke/WAI-State.json'))
q = state.get('wheel', {}).get('qualifiers', {})
if not q or all(len(v) == 0 for v in q.values()):
    print("⚠ Qualifiers not set — add wheel.qualifiers to help the hub KB match relevant learnings to this project.")
    print("  Fields: project_types, languages, frameworks, domains, themes")
```

### Step 1c: Navigator Startup (silent if hub absent)

Sync Navigator recommendations from hub and check catalog TTL.

```python
import json, datetime, os, shutil

nav_dir = 'WAI-Spoke/advisors/navigator'
cache_path = f'{nav_dir}/catalog-cache.json'
rec_local = f'{nav_dir}/recommendations-current.json'
now = datetime.datetime.now(datetime.timezone.utc)

# Catalog TTL check (warn only)
if os.path.exists(cache_path):
    cache = json.load(open(cache_path))
    if cache.get('cached_at'):
        age_h = (now - datetime.datetime.fromisoformat(cache['cached_at'])).total_seconds() / 3600
        if age_h > cache.get('ttl_hours', 24):
            print(f'⚠ Navigator catalog cache stale ({age_h:.0f}h old) — will refresh on next nightly run.')

# Usage limit warnings from spoke-local tracking
# Reads usage_summary written by navigator_spoke_sync.py into catalog-cache.json
if os.path.exists(cache_path):
    cache = json.load(open(cache_path))
    usage_summary = cache.get('usage_summary')
    if usage_summary is None:
        # catalog-cache exists but no usage_summary — limits not yet configured or sync not run
        if os.path.exists(f'{nav_dir}/limits-config.json'):
            print('Navigator: limit data unavailable — run spoke sync to populate usage_summary')
    elif not usage_summary.get('limits_available'):
        print('Navigator: limit data unavailable (create limits-config.json to enable per-model tracking)')
    else:
        for entry in usage_summary.get('entries', []):
            if entry.get('at_threshold'):
                pct_int = int(entry['pct'] * 100)
                alt = entry.get('alternative_model_id') or 'alternative model'
                print(f"Navigator: ⚠ {entry['model_id']} {entry['window_type']} usage: {pct_int}% ({entry['used']}/{entry['limit']} {entry['unit']}) -- recommend {alt}")
        # Silent when all models are below threshold

# Recommendations sync from hub (silent skip if hub absent)
try:
    state = json.load(open('WAI-Spoke/WAI-State.json'))
    hub_path = state.get('_hub', {}).get('path') or state.get('hub_path')
    if hub_path:
        hub_rec = os.path.join(hub_path, 'WAI-Hub/advisors/navigator/recommendations-current.json')
        if os.path.exists(hub_rec):
            shutil.copy2(hub_rec, rec_local)
            rec = json.load(open(rec_local))
            if os.path.exists(cache_path):
                cache = json.load(open(cache_path))
                cache['recommendations_pulled_at'] = now.isoformat()
                cache['recommendations_valid_through'] = rec.get('valid_through')
                json.dump(cache, open(cache_path, 'w'), indent=2)
            n_profiles = len(rec.get('profiles', {}))
            valid_through = rec.get('valid_through')
            if valid_through and datetime.datetime.fromisoformat(valid_through) > now:
                print(f'Navigator: {n_profiles} recommendation profiles current')
            else:
                print(f'⚠ Navigator: recommendations stale — hub nightly run may be overdue')
except Exception:
    pass  # hub not connected or file absent — silent skip

# Availability determination — detect embedded_ai_mode, show appropriate Navigator line
try:
    import glob
    rec_path = 'WAI-Spoke/advisors/navigator/recommendations-current.json'
    state_path = 'WAI-Spoke/WAI-State.json'
    embedded_ai_tags = {'ai-integration', 'embedding-ai', 'llm-feature', 'ai-tool'}
    if os.path.exists(rec_path) and os.path.exists(state_path):
        rec = json.load(open(rec_path))
        wai_state = json.load(open(state_path))
        profiles = rec.get('profiles', {})

        # Detect embedded_ai_mode from top ready work queue item
        work_queue = wai_state.get('_work_queue', {})
        top_ready = next(
            (item for item in sorted(work_queue.get('items', []), key=lambda x: x.get('roi', 0), reverse=True)
             if item.get('readiness') == 'ready'),
            None,
        )
        is_embedded_ai = bool(top_ready and embedded_ai_tags.intersection(top_ready.get('tags', [])))

        # Count available providers (providers with at least one slot in profiles)
        provider_slots: dict[str, list] = {}
        for profile_id, profile_data in profiles.items():
            for slot_val in profile_data.get('slots', {}).values():
                if isinstance(slot_val, dict):
                    prov = slot_val.get('provider', '')
                    provider_slots.setdefault(prov, []).append(slot_val)
        available_providers = sorted(p for p in provider_slots if p)
        total_model_count = sum(len(v) for v in provider_slots.values())

        if is_embedded_ai:
            # Full landscape format
            best = None
            cost = None
            for profile_data in profiles.values():
                for slot_name, slot_val in profile_data.get('slots', {}).items():
                    if not best and isinstance(slot_val, dict):
                        best = slot_val
                    if slot_name in ('cost', 'haiku') and isinstance(slot_val, dict) and not cost:
                        cost = slot_val
            best_id = best.get('model_id', '') if best else 'unknown'
            best_prov = best.get('provider', '') if best else ''
            cost_id = cost.get('model_id', '') if cost else best_id
            print(f'Navigator: Full landscape: {len(available_providers)} providers, {total_model_count} models | Best: {best_id} ({best_prov}) | Cost: {cost_id} | See recommendations-current.json')
        else:
            # Default mode — best recommendation + unlock hint
            best_model_id = best_profile = best_score = best_prov = None
            for profile_id, profile_data in profiles.items():
                default_slot = profile_data.get('slots', {}).get('default') or next(iter(profile_data.get('slots', {}).values()), None)
                if isinstance(default_slot, dict):
                    score = default_slot.get('score', 0)
                    if best_score is None or score > best_score:
                        best_score = score
                        best_model_id = default_slot.get('model_id', '')
                        best_prov = default_slot.get('provider', 'anthropic')
                        best_profile = profile_id

            # Providers not available locally (key absent) → show unlock count
            anthropic_always = ['anthropic']  # always available in Claude Code
            locked = [p for p in available_providers if p not in anthropic_always and p != best_prov]
            unlock_suffix = f' + {len(locked)} others — configure API keys to unlock' if locked else ''
            print(f'Navigator: Available: {best_model_id} ({best_profile}, score={best_score}) [{best_prov}]{unlock_suffix}')
except Exception:
    pass
```

### Step 1d: Hub Signals Inbox (skip if HUB SIGNALS = 0)

When `hub_signals_pending > 0` in session-init (or wakeup-brief), process each signal in `{hub_path}/WAI-Hub/signals/incoming/framework/` with two suppression checks before incorporating:

```python
import json, os, glob

state = json.load(open('WAI-Spoke/WAI-State.json'))
wheel_name = state.get('wheel', {}).get('name', '')
hub_path = state.get('_hub', {}).get('path') or state.get('hub_path', '')
inbox = os.path.join(hub_path, 'WAI-Hub/signals/incoming/framework') if hub_path else ''

# Build local signal ID index (all subdirs under bytype/signal/)
local_ids = set()
for f in glob.glob('WAI-Spoke/lugs/bytype/signal/**/*.json', recursive=True):
    try:
        d = json.load(open(f))
        local_ids.add(d.get('id', ''))
    except Exception:
        pass

if inbox and os.path.isdir(inbox):
    for sig_file in glob.glob(os.path.join(inbox, '*.json')):
        try:
            sig = json.load(open(sig_file))
            sig_id = sig.get('id', os.path.basename(sig_file))
            source_spoke = sig.get('source_spoke', '')

            # Dedup: skip if ID already incorporated locally
            if sig_id in local_ids:
                print(f'  [skip-dedup] {sig_id}')
                continue

            # Boomerang: skip if this spoke originated the signal
            if source_spoke and source_spoke == wheel_name:
                print(f'  [skip-boomerang] {sig_id} (originated here)')
                continue

            print(f'  [new] {sig_id} — {sig.get("title", sig.get("subject", "?"))[:80]}')
        except Exception as e:
            print(f'  [error] {sig_file}: {e}')
```

**Note:** `source_spoke` is a required field on all signal lugs. Without it, boomerang suppression cannot fire — the signal will be re-incorporated by the originating spoke on every wakeup.

### Step 2: Execute Full Protocol

Use `Read` to load `templates/commands/wai-full.md`, then execute all steps in that document.

---

*Fast path: 0 tool calls, ~15s. Brief path: 1 tool call. Full protocol in wai-full.md (loaded on demand).*


Convergence rules for all tools:
- Finish the WAI Point briefing before pausing for teaching approval or any other side action.
- During wakeup, inspect teachings using filenames and lightweight header/frontmatter fields only. Do NOT read full teaching bodies unless the user explicitly asks to review them now.
- If pending teachings exist, include them in the briefing under a compact "Pending Teachings" section, then ask what to do next.
- **Teachings and incoming lugs are first-class priority.** If either is non-zero at wakeup, address them before entering work queue mode. Do not skip or defer to the next session.
- **Post-adoption basher doctor check.** After the user confirms adoption of any teaching: check if `WAI-Spoke/basher.json` exists in this spoke. If it does, emit immediately after adoption completes: `Recommended: run \`basher doctor\` to apply latest basher configuration to this spoke. Restart session if prompted.`


## Initiatives & Theme Health

**Initiatives** group related epics for completion tracking. **Themes** are the 7 health dimensions scored over time.

To surface the full scorecard: `/wai-initiative`

Quick summary at wakeup:
- Show count of epics per initiative (open / in_progress / completed)
- Flag any theme with zero active epic coverage as "neglected"
- Flag any epic with no `themes[]` field as "untagged"

Data source: `WAI-Spoke/initiatives/index.json`

---

Output contract for all tools:
- Output the completed WAI Point briefing directly; do not narrate shell probes or bootstrap steps before it.
- Keep the post-brief closeout to one short readiness line such as `Wake complete. Ready to work.`
- Do not replace the briefing with a numbered next-steps plan unless the user explicitly asks for planning.
- If teachings or stale-task decisions need approval, list them compactly under `Pending Items` inside the briefing rather than stopping early.
