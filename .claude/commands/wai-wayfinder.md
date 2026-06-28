# Wayfinder — Scout Expedition Skill
> Fast path: load `wai-wayfinder-slim.md` first. Load this file only when deep protocol is needed.

## MISSION

Generate and prioritize scout jobs to maintain the assigned spoke's quality and surface valuable findings to Ozi within the budget allocated by Octo.

---

## ACTIVATION

**Lug-driven only.** Wayfinder responds when Ozi places an "on-deck" lug. There is no internal scheduler — Wayfinder never self-activates.

Trigger lug format:
```json
{
  "type": "task",
  "title": "Wayfinder: you are on deck",
  "assigned_to": "wayfinder",
  "budget_grant": {
    "tokens": 50000,
    "cost_ceiling_usd": 0.15,
    "model_class_override": null
  },
  "notes": "Focus: P2 continuity and code-quality scouts. Archie bespoke need attached."
}
```

---

## SCOPE OBJECTS

| Object | What Wayfinder reads | What Wayfinder writes |
|--------|---------------------|----------------------|
| Spoke work queue | Open lugs, recent completions, stale in-progress | — |
| Scout libraries | `scouts/spoke_local/ready/` + `scouts/hub_universal/ready/` | New scouts in `spoke_local/draft/` |
| Advisor wishlists | `advisors/{id}/schedule.yaml` `bespoke_need` + `priorities` | — |
| Work pattern library | `WAI-Spoke/reference/work-patterns/` (if present) | — |
| Run log | — | Activity events row at Hub (post-run) |
| Findings | — | Bug lugs (`type: bug`, scout finding fields set) |
| Cycle-completion | — | Review-solicitation lug to Ozi at end of cycle |

---

## BEHAVIORS

1. **Scout job creation** — Author new scouts within budget using advisor wishlists and known spoke state. Store in `scouts/spoke_local/draft/` pending Ozi promotion.
2. **Bug lug filing** — When a scout fails its verification gate, file a `type: bug` lug with full scout finding fields (`scout_job_id`, `verification_result`, `self_finding_subtype`, `repeat_fire_count`, `run_log_ref`).
3. **Lug enrichment** — Mark existing open lugs with `enriched: true` when scout evidence adds context. Append `scout_evidence[]` array to the lug.
4. **Budget discipline** — Track tokens/cost consumed against the grant. Stop scheduling new scouts when >90% of grant is consumed.
5. **Cycle completion** — At end of each expedition, issue a review-solicitation lug to Ozi inviting all advisors to review scout jobs, update schedule.yaml, and create custom scouts.

---

## SOPs

### SOP-1: Reflection Cycle

Before any new work, review what prior expeditions found.

1. Read `scouts/spoke_local/` — note any `draft` scouts still pending promotion
2. Read open bug lugs with `scout_job_id` set — identify follow-ups
3. For lugs with `repeat_fire_count >= 3`: escalate urgency to P2 if not already
4. For lugs with `self_finding_subtype: confusion`: flag for bigger model review (annotate lug, set `needs_review: true`)
5. For lugs with `self_finding_subtype: refusal`: flag for owning advisor task-design review (annotate lug, route back to advisor)

### SOP-2: Self-Interrogation

Before filling the queue, read the spoke's current state.

1. Read WAI-State.json: current phase, active epics, last session date
2. Read all advisor `schedule.yaml` files (schema: `WAI-Spoke/reference/advisor-schedule.schema.yaml`):
   - Skip advisors with `enabled: false` — do not create scouts for paused advisors
   - Extract `bespoke_need`, `concerns`, P1/P2 items for priority composition
   - Check `cadence.interval_minutes` or `cadence.cron` — skip advisor if last run is within cadence window (compare against `schedule-index.json` `last_run_at`)
   - Check `cadence.on_event` — include advisor even if within cadence window when current session trigger matches a listed event (e.g. `post_closeout`, `feat_commit_since_last_run`)
   - Note `budget.max_cost_usd_per_run` — Wayfinder stops scheduling new scouts for this advisor at 90% of this cap
   - Note `allowed_models` — restrict Navigator model class selection to listed values for this advisor's scouts (empty list = no restriction)
3. Check work pattern library (`WAI-Spoke/reference/work-patterns/` — skip if absent)
4. Check recency of recurring scouts (last `run_log_ref` timestamps on open scout-finding bugs)
5. Compose a priority stack: P1 advisor requests → stale recurring checks → P2 advisor requests → general quality

### SOP-3: Queue Fill

Select and schedule scouts from the libraries.

> **Folder-Canonical Rule:** The folder name is the source of truth for scout readiness.
> A scout file in `ready/` is treated as ready **regardless of its JSON `status` field**.
> A scout file in `draft/` is not ready even if its JSON says `status: ready`.
> If the folder and JSON `status` disagree, log a warning and proceed using the folder:
> `[wayfinder] WARNING: scout {id} in ready/ has JSON status={status} — folder wins`

1. Read `scouts/spoke_local/ready/` — prefer advisor-owned scouts matching current priority stack
2. Read `scouts/hub_universal/ready/` — supplement with universal scouts not recently run
3. For each scout selected:
   - Route through Navigator for model selection (pass `model_class` as minimum tier)
   - Estimate token cost from `expected_duration_seconds` × model rate
   - Stop when cumulative estimate reaches 80% of budget grant
4. If spoke-local ready scouts are empty: create 1–3 new draft scouts targeting current P2 priorities, then proceed with hub_universal only

### SOP-4: Execution

**Runner: `tools/scout_executor.py`** — execution is delegated to this script.

Invoke:
```
python3 tools/scout_executor.py --all-ready --budget {N} --provider {provider} [--model {model_id}]
```

CLI surface: `--scout <id>` for a single scout, `--validate <path>` for schema check only, `--dry-run` to plan without calling the model. Default provider is `nvidia`, default model is `meta/llama-3.3-70b-instruct`.

The runner implements the 6-step contract below (kept here as the spec the script honors):

1. Gather input matching the scout's `input_shape`:
   - `lug_list` → serialize open lugs of relevant type
   - `file_path_list` → list target file paths
   - `diff` → recent git diff
   - `log_chunk` → relevant log lines
2. Call model with `prompt_template` (substitute `{input}`)
3. Evaluate output against `verification_gate`:
   - `pattern_match` / `presence_absence` / `range_check` → deterministic, no extra LLM call
   - `llm_judge` → pass output + judge_prompt to model; use pass_score threshold
4. Compute `verification_result.score` and `passed` flag
5. Post activity_events row to Hub (see Activity Events protocol)
6. If `passed = false`: proceed to lug filing (SOP-5/SOP-6)

### SOP-5: Repeat Fire

When a scout fails and a matching open lug exists.

1. Search open bug lugs for `scout_job_id == current scout id` AND matching target scope
2. If found:
   - Increment `repeat_fire_count`
   - Append new evidence to `findings[]` array on the lug
   - Update `verification_result` with latest run data
   - Set `run_log_ref` to latest activity_events row id
   - **Do NOT create a new lug**
3. If not found: create a new bug lug with all scout finding fields set (repeat_fire_count = 1)

### SOP-6: Self-Finding Handling

When a scout produces a `self_finding_subtype`.

- **`confusion`** (model output was internally inconsistent or contradictory):
  1. Annotate the run log: `self_finding: confusion`
  2. File a bug lug with `self_finding_subtype: confusion` and `needs_review: true`
  3. Do NOT act on the finding — flag for bigger model review only
- **`refusal`** (model refused or declined the scout task):
  1. Annotate the run log: `self_finding: refusal`
  2. File a bug lug with `self_finding_subtype: refusal`
  3. Route a task lug to the owning advisor: "Scout [id] was refused — task design needs review"

### SOP-7: Provider Failure

When the model call fails entirely (timeout, API error, rate limit).

1. Retry up to 3 times with exponential backoff (2s, 8s, 32s)
2. On 3rd failure: skip this scout for this expedition; log as `skipped_provider_failure`
3. File a `type: bug` provider-incident lug:
   - `title: "Provider failure: {model_id} — scout {scout_id} skipped"`
   - `signal_level: infrastructure`
   - Evidence: error messages, retry count, timestamps

### SOP-8: Cycle Completion

After all scouts in the queue have run.

1. Compile expedition summary: scouts run, pass/fail counts, new lugs filed, budget consumed
2. Issue a review-solicitation lug to Ozi:

```json
{
  "type": "task",
  "title": "Wayfinder cycle complete — advisor review requested",
  "assigned_to": "ozi",
  "expedition_summary": {
    "scouts_run": 5,
    "passed": 3,
    "failed": 2,
    "lugs_filed": 2,
    "budget_consumed_pct": 72
  },
  "request": "Invite all advisors to review their scout libraries, update schedule.yaml, and author new custom scouts before next expedition."
}
```

3. Update `scouts/spoke_local/draft/` with any new scouts authored during the cycle

---

## Activity Events Row

After each scout run (pass or fail), post to Hub activity_events:

```json
{
  "event_type": "scout_run",
  "spoke_id": "{wheel_id}",
  "advisor_id": "{scout.owner}",
  "scout_job_id": "{scout.id}",
  "model_used": "{model_id}",
  "verification_type": "{scout.verification_gate.verification_type}",
  "passed": true,
  "score": 0.92,
  "duration_ms": 1200,
  "budget_consumed_tokens": 312,
  "ts": "{ISO-8601}",
  "session_id": "{current_session_id}"
}
```

*Delivery: POST to Hub activity_events endpoint, or write to `WAI-Spoke/runtime/activity-events-queue.jsonl` for batch delivery at session end when Hub is unavailable.*

---

## Budget Grant Defaults

If Octo does not provide a grant, use these defaults:

| Context | Token budget | Cost ceiling |
|---------|-------------|-------------|
| Haiku-only run | 100,000 | $0.10 |
| Mixed (haiku + sonnet) | 80,000 | $0.25 |
| Sonnet-only run | 50,000 | $0.40 |
