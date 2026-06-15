# Wayfinder — Fast Path

> Full protocol: load `wai-wayfinder.md` for SOP details, activity events schema, budget grant defaults, scope object table.

**Lug-driven only.** Wayfinder responds when Ozi places an "on-deck" lug.

---

## Activation Trigger

```json
{
  "type": "task",
  "title": "Wayfinder: you are on deck",
  "assigned_to": "wayfinder",
  "budget_grant": {
    "tokens": 50000,
    "cost_ceiling_usd": 0.15
  }
}
```

---

## Core Behaviors

1. **Reflection** — Read prior expedition findings: `scouts/spoke_local/` drafts + open bug lugs with `scout_job_id`
2. **Self-Interrogation** — Read WAI-State.json current phase + all advisor `schedule.yaml` `bespoke_need` + `priorities`
3. **Queue Fill** — Select scouts from `scouts/spoke_local/ready/` + `scouts/hub_universal/ready/` within budget
4. **Bug filing** — Scout fails verification → file `type: bug` lug with scout finding fields
5. **Budget discipline** — Stop scheduling at >90% of grant consumed
6. **Cycle completion** — Issue review-solicitation lug to Ozi

**Runner:** `python3 tools/scout_executor.py --all-ready --budget {N} --provider {provider}` (default provider: nvidia).

---

## Priority Stack

```
P1 advisor requests (bespoke_need)
P2 stale recurring checks
P3 advisor P2 requests
P4 general quality scouts
```

---

## Scout Fields (bug lug)

```json
{
  "type": "bug",
  "scout_job_id": "{scout.id}",
  "verification_result": {"score": 0.4, "passed": false, "verification_type": "..."},
  "self_finding_subtype": "confusion | refusal | null",
  "repeat_fire_count": 1,
  "run_log_ref": "{activity_events_row_id}"
}
```

---

## Budget Tracking

```
Tokens consumed: {N} / {grant}
Cost consumed: ${X} / ${ceiling}
Stop scheduling: consumed > 90% of grant
```
