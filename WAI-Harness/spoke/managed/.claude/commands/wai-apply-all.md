# WAI Apply All — Parallel Dispatch Skill

Dispatches all ready lugs in parallel worktree-isolated sub-agents, with collision detection and batch sequencing.

---

## Step 1: Build batch plan

```bash
python3 tools/batch_planner.py --json
```

Capture the JSON output. If `ready_count == 0`: output `No ready items for parallel dispatch.` and stop.

## Step 2: Present plan

Display:
```
Apply All — Parallel Dispatch Plan
  Ready items: {ready_count}
  Batch 1 ({N} items, parallel): {items joined by ", "}
  Batch 2 ({N} items, sequential after B1): {items}   [if exists]
  Collision pairs: {collision_pairs or "none"}
[C]onfirm / [S]kip
```

Wait for user confirmation. On **S**: stop.

## Step 3: Dispatch Batch 1

For each item in `batches[0].items`, invoke the Agent tool with:

```
description: "Implement {lug_id}"
isolation: "worktree"
run_in_background: true   (for all items except the last in the batch)
prompt: |
  Implement lug `{lug_id}`.
  1. Read the lug file from `WAI-Spoke/lugs/bytype/` (find it with: find WAI-Spoke/lugs/bytype -name '{lug_id}.json')
  2. Execute the `execute` steps exactly as written.
  3. Run the `verify` steps to confirm the implementation works.
  4. Update the lug status to `completed` and move it from open/ to completed/.
  5. Write a one-line result to stdout: `{lug_id}: DONE | {summary}` OR `{lug_id}: FAILED | {reason}`
  Do not run closeout. Do not push to git.
```

All batch 1 items dispatch concurrently (run_in_background=true for all except the last, which is foreground to collect completion).

## Step 4: Aggregate Batch 1 results

Collect each agent's result line. For each:
- **DONE**: confirm lug is in `completed/` (verify the file moved)
- **FAILED**: keep lug in `open/`, set `_last_attempt_failed: true` on the lug JSON

Display: `Batch 1 complete: {N_done}/{N_total} succeeded.`

If any failures: list them. Ask `[C]ontinue to Batch 2 / [S]top`.

## Step 5: Continue batches

If `batches[1]` exists AND batch 1 had no failures (or user chose C):
- Repeat Steps 3–4 for `batches[1]`, then `batches[2]`, etc., in order.
- Each subsequent batch waits for the prior batch to complete before dispatching.

## Step 6: Final summary

```
Apply All complete.
  Dispatched: {total_dispatched}
  Succeeded:  {succeeded}
  Failed:     {failed} [{failed_ids}]
  Next: run /wai-status to see updated queue.
```

If `succeeded > 0`: offer to run closeout (`/wai-closeout`) to commit the results.

---

## Notes

- Each sub-agent works in an isolated git worktree — no shared working tree conflicts.
- Sub-agents do not run closeout or push; the parent session handles commit after aggregation.
- Collision detection is handled by `batch_planner.py`: lugs sharing `target_files` go in separate batches automatically.
- `blocked_by` constraints are respected: a lug in Batch 2 will not dispatch until Batch 1 is complete.
