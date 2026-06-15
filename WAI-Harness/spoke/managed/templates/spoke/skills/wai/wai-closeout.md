# Skill: WAI Closeout (Spoke Copy)

## Spoke-Local Closeout Steps

This file contains spoke-specific closeout instructions. The main closeout protocol
lives at `templates/commands/wai-closeout.md`.

### 9b-2. Spoke Telemetry Rollup

Run spoke-telemetry-closeout skill (`templates/spoke/skills/wai/spoke-telemetry-closeout.md`):

1. Read session `track.jsonl` → extract model_telemetry entries
2. Aggregate into `model_usage[]` by model_id
3. Compute dominant_model, work_type_distribution, peak_hour_utc
4. Write rollup to `WAI-Spoke/telemetry/session-{session_id}-rollup.json`
5. Deliver rollup to hub Assessor inbox: `{hub_path}/WAI-Hub/advisors/assessor/inbox/{session_id}-rollup.json`
   If hub unreachable: note in session record, do not block.

Report: "Telemetry rollup written for session {session_id}. Delivered to Assessor."
