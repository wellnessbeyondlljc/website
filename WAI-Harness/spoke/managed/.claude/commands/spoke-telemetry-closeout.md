# Skill: Spoke Telemetry Closeout

## Purpose

At closeout, collect model usage telemetry from the current session, aggregate it
into a session rollup, write it to `WAI-Spoke/telemetry/`, and deliver it to the
hub Assessor advisor inbox via the signal bulletin pipeline.

## Invocation Context

Called during `/wai-closeout` **before** hub signal delivery (Step 9c).
Runs after lug closeout and before any outgoing delivery.

## Rollup Schema

```json
{
  "session_id": "session-YYYYMMDD-HHMM",
  "spoke_id": "from WAI-State.wheel.spoke_id",
  "rollup_type": "spoke_telemetry",
  "generated_at": "ISO8601",
  "model_usage": [
    {
      "model_id": "string — e.g. claude-sonnet-4-6",
      "turn_count": 0,
      "total_input_tokens": 0,
      "total_output_tokens": 0,
      "estimated_cost_usd": 0.00,
      "work_types": ["coding", "planning", "analysis"],
      "avg_complexity": null
    }
  ],
  "dominant_model": "string — model_id with highest turn_count",
  "session_vibe": "string | null — from WAI-State._session_state.current_vibe",
  "work_type_distribution": {
    "coding": 0,
    "planning": 0,
    "analysis": 0,
    "debugging": 0,
    "ideation": 0,
    "writing": 0
  },
  "peak_hour_utc": "HH — hour with most turns",
  "total_turns": 0,
  "total_lugs_touched": 0,
  "routed_to": "ASSESSOR",
  "scoring_method": null,
  "quality_score": null
}
```

## Processing Steps

1. Read `session_id` from `WAI-State._session_state`
2. Read `track.jsonl` and extract entries with `model_telemetry` data
3. Aggregate by `model_id`:
   - `turn_count`: count of entries per model
   - `total_input_tokens`: sum (0 if absent)
   - `total_output_tokens`: sum (0 if absent)
   - `estimated_cost_usd`: best-effort from token counts × pricing (0.00 if uncertain)
   - `work_types`: unique set inferred from lug types (see inference table)
   - `avg_complexity`: mean of complexity values (null if none)
4. Compute derived fields:
   - `dominant_model`: model_id with highest turn_count
   - `session_vibe`: read from `WAI-State._session_state.current_vibe` (null if absent)
   - `work_type_distribution`: count entries by inferred work type
   - `peak_hour_utc`: mode hour from turn timestamps
   - `total_turns`: sum of all turn_counts
   - `total_lugs_touched`: count distinct lug_ids in track entries
5. Write rollup to `WAI-Spoke/telemetry/session-{session_id}-rollup.json`
6. Deliver rollup to hub with `routed_to: ASSESSOR`:
   Write to `{hub_path}/WAI-Hub/advisors/assessor/inbox/{session_id}-rollup.json`
   If hub unreachable: note in session record, do not block closeout.

## Work Type Inference Priority

When `work_type` is not explicitly set, infer from lug type + vibe:

| Priority | Condition | Inferred work_type |
|---|---|---|
| 1 | bug/finding lug | debugging |
| 2 | impl/task lug + build/grind vibe | coding |
| 3 | epic/feature lug | planning |
| 4 | decision lug | analysis |
| 5 | think vibe + no lug | ideation |
| 6 | policy/foundation lug | writing |
| 7 | default | analysis |

## Notes

- `model_telemetry` in track.jsonl entries is **optional** — entries without it are counted
  in `total_turns` but not in `model_usage`.
- `latency_ms` is best-effort: set to null unless platform metadata provides it.
- `estimated_cost_usd` is 0.00 unless a model-registry with pricing is available.
- This skill produces one rollup per session. The Assessor aggregates across sessions.
- `scoring_method` and `quality_score` are null at generation time — the Historian
  backfills these during Gardener Pass 2.
