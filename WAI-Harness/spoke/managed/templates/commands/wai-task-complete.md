# WAI Task Complete

**Micro-protocol.** Runs when you finish a lug mid-session. It does two things: (1) captures the insight *at the moment of action* into the staging buffer (so closeout doesn't re-compose it from decayed/compacted context), and (2) surfaces the next best work by ROI so momentum doesn't stall.

## Trigger

Invoke when, during a session (not yet in closeout):
- You set a lug's status to `completed` and write a `lug_completed` track event, **or**
- You write a `goal_completed` event for a goal set this session.

Skip if: the work queue has 0 ready items, the only ready item is the one just completed, you are already in the closeout phase, or `WAI-State._session_state.skip_task_complete_surface == true`.

## Step 1 — Capture the insight now (partial staging)

Write or merge `WAI-Spoke/runtime/closeout-staging.json` with `type: "partial"` — the pre-composed landing zone closeout will harvest:

```json
{
  "schema_version": "2.0",
  "type": "partial",
  "session_id": "{current_session_id}",
  "partial_lug_id": "{just-completed lug_id}",
  "partial_summary": "{one line: what was just done + why it matters}",
  "commit_message": "wip: {session_id} — {partial_summary} [partial]",
  "lugs_completed": ["...prior...", "{just-completed lug_id}"],
  "composed_at": "{now ISO UTC}",
  "version": null, "tag": null, "lug_id": null, "resume_note": null, "work_done": null
}
```

If the file already exists with `type: "partial"` for this session: append to `lugs_completed[]` and update `partial_lug_id` / `partial_summary` to the latest. **Do the work at the time of action** — this is the principle: capture the insight while context is fresh, insulating against compaction and memory decay.

## Step 2 — Surface the next ROI work

Read `WAI-State.json._work_queue.items`. Filter to `readiness == "ready"` AND `id` not in this session's `lugs_completed`. Sort by `roi` (or ROI score) descending. Take the top 2 and show:

```
✓ Completed: {just-completed lug title}

Next ready (by ROI):
[1] {lug_id} — {title}   (ROI {score} · {effort} · {model_fit})
[2] {lug_id} — {title}   (ROI {score} · {effort} · {model_fit})

[C]ontinue with [1]  ·  [K]eep current thread  ·  [S]kip
```

## Step 3 — Act on the choice

- **[C] (or "continue with N"):** load that lug from `bytype/{type}/open/`, set it active, write a `goal_set` event, begin.
- **[K]:** resume the current thread; no state change.
- **[S]:** no action; continue the session organically.

> Closeout harvests the `partial` staging buffer (its `commit_message` + `lugs_completed`) instead of re-composing — see `wai-closeout.md` partial-staging recovery.
