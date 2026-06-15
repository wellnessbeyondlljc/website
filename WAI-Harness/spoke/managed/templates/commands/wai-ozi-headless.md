# WAI Ozi Headless Runner

## Context

OziHeadlessRunner (OHR) is the headless execution controller for spoke lugs. It runs in three phases:
- **Phase 0** — State assessment: counts ready/blocked/stalled lugs, reads advisor schedules
- **Phase 2** — Signal triage: routes undelivered signals to outbox
- **Phase 3** — Lug execution: dispatches eligible lugs via `claude --print` subprocesses

Use OHR when you want lugs to run unattended (nightly, scheduled) or when you want to batch-execute haiku-fit lugs without manual intervention. After an OHR run, use `/wai-ozi-review` to step through results.

## Invocation

```bash
python3 tools/ozi_autopilot.py --spoke-path . --budget 3
```

## Dry-run

The `--dry-run` flag shows what would execute without modifying any files:

```bash
python3 tools/ozi_autopilot.py --spoke-path . --budget 10 --dry-run
```

Dry-run output includes dispatch order (urgency_tier ASC → roi DESC → wave ASC) and the model that would be used for each lug.

## Output format

OHR prints JSON to stdout on completion:

```json
{
  "completed": ["lug-id-a", "lug-id-b"],
  "teachings_adopted": 0,
  "gastown_pending": false,
  "advisors_run": [],
  "errors": []
}
```

| Field | Description |
|-------|-------------|
| `completed` | IDs of lugs that dispatched successfully |
| `teachings_adopted` | Count of teachings auto-adopted during the run |
| `gastown_pending` | Whether work was queued to Gastown |
| `advisors_run` | Advisor IDs that executed during Phase 0 |
| `errors` | Any errors encountered (phase + message) |

## Eligibility rules

OHR skips lugs that are:
- Type: `epic`, `idea`, `policy`, `audit`, `directive`, `session-summary`, `signal`
- `risk_tier: critical`
- `execution_mode: manual`
- Still blocked (`blocked_by` contains unresolved IDs)

## UAT

After a real (non-dry-run) OHR execution, run `/wai-ozi-review` to step through completed items and accept, defer, or reject each outcome.
