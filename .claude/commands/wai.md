# WAI Wakeup Protocol

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
│  {If CONTEXT HEALTH 'Savepoint: PENDING': ⚑ Savepoint: [lug_id] — [resume_note]}
│  Intent: {intent} — {intent_label}   ← If intent set; otherwise: Vibe: none  |  Context: unknown — run /context
│  {If TEACHINGS New > 0: Teachings: N pending (Path A/B)}
│  {If HUB SIGNALS > 0: Hub signals: N framework}
│  {If recommendations valid: Navigator: N profiles current | If stale or null: ⚠ Navigator: recommendations stale}
│  {If TOOL ADVISOR audit due: ⚠ Tool audit due}
│  {If context feeds stale: Context feeds: N stale}
│  {If HISTORIAN ADVICE present: Historian: {first bullet}}
│  {Active feedback: top-3 from MEMORY.md feedback entries — see Step 3b}
│  Next: {first item from NEXT ACTIONS}
└─ Ready to work.
```

**2b. Intent router** (skip entirely if SESSION_INTENT absent — proceed to Step 3):

| Intent | Max tools | Action |
|--------|-----------|--------|
| `savepoint` | 3 | **If `SAVEPOINT_ALREADY_CONFIRMED = true`:** skip prompt — display `⚑ Savepoint confirmed at session start — continuing {lug_id}`, then read WAI-State.json `_savepoint` + lug file + append track, set lug status to `resumed`, display resume_note. **If false:** show `[C]ontinue savepoint / [F]ull wakeup?` — on C: same auto-proceed; on F: clear `_savepoint` from WAI-State.json, fall through to FULL PROTOCOL. |
| `implement` | 1 | Read WAI-State.json. Display top-3 ready lugs by ROI. |
| `refinement` | 1 | Read WAI-State.json. Display needs_refinement items. |
| `teachings` | 1 | List `WAI-Spoke/seed/ingest/` teaching dir. Display pending count. |
| `explore` | — | Skip router. Proceed to Steps 3+4 normally. |
| `closeout` | 0 | Display closeout reminder. Invoke `/wai-closeout`. |
| `full` | — | If `_savepoint` is pending in WAI-State.json: clear it first (set `_savepoint.status = null`). Fall through to FULL PROTOCOL. |

After routing, **do not ask for vibe**. Proceed directly to work.

**2c. Savepoint intercept** (only when `SESSION_INTENT` is absent — skip if already handled by Step 2b):

If `CONTEXT HEALTH` in session-init contains a line beginning with `Savepoint: PENDING`:
- Extract `lug_id` and `resume_note` from `Savepoint: PENDING [lug_id] — resume_note`.
- Display:

```
⚑ Savepoint detected: [lug-id]
  Resume: [resume_note]
  [C]ontinue (load lug only ~5k tokens) / [F]ull wakeup
```

If user chooses **C**:
1. Read the savepoint lug JSON only (1 tool call)
2. Read last 2 track entries from current `track_path` (1 tool call)
3. Write `WAI-State.json`: set `_savepoint.status = "resumed"` (1 write)
4. Display: `Continuing [lug-id]. Context: ~5k tokens. [resume_note]`
5. Begin work — skip Steps 3 and 4 entirely

If user chooses **F**:
1. Write `WAI-State.json`: clear `_savepoint` (set to `{}`)
2. Continue normally to Step 3

**3. Ask:** `Vibe? (build / fix / think / grind / ship / refine) [skip]`
**After user responds:** Write chosen vibe (or `null` if skipped) to `WAI-State.json._session_state.current_vibe`. Example: `{"event": "vibe_set", "vibe": "build", "ts": "..."}`

**3b. Active Feedback Surface:** Scan the `MEMORY.md` already loaded in context. Find all entries of type `feedback`. Pick the top 3 by most-recently-updated or most frequently-triggered. Output one compact line:

```
Active feedback (N): [rule-1 short label] | [rule-2 short label] | [rule-3 short label]
```

This line closes the apply gap — feedback entries are loaded at wakeup AND explicitly surfaced so the agent acknowledges them before starting work. If fewer than 3 feedback entries exist, show all of them. If MEMORY.md has no feedback entries, skip this line silently.

**4. Work Queue Interactive Mode:** After vibe prompt, if `_work_queue.items` has `>=1` ready item, display top-3 by ROI.

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
│  {If teachings_pending > 0: Teachings: N pending}
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

### Step 2: Execute Full Protocol

Use `Read` to load `templates/commands/wai-full.md`, then execute all steps in that document.

---

*Fast path: 0 tool calls, ~15s. Brief path: 1 tool call. Full protocol in wai-full.md (loaded on demand).*


Convergence rules for all tools:
- Finish the WAI Point briefing before pausing for teaching approval or any other side action.
- During wakeup, inspect teachings using filenames and lightweight header/frontmatter fields only. Do NOT read full teaching bodies unless the user explicitly asks to review them now.
- If pending teachings exist, include them in the briefing under a compact "Pending Teachings" section, then ask what to do next.


Output contract for all tools:
- Output the completed WAI Point briefing directly; do not narrate shell probes or bootstrap steps before it.
- Keep the post-brief closeout to one short readiness line such as `Wake complete. Ready to work.`
- Do not replace the briefing with a numbered next-steps plan unless the user explicitly asks for planning.
- If teachings or stale-task decisions need approval, list them compactly under `Pending Items` inside the briefing rather than stopping early.
