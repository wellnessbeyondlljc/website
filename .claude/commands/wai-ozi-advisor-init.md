# wai-ozi-advisor-init — Ozi Advisor Init Routine

**Skill ID:** wai-ozi-advisor-init  
**Spec:** spec-ozi-advisor-init-routine-v1  
**Trigger:** new spoke in hub-registry.json OR `ozi init-advisors --spoke <spoke_id>`  
**Model:** sonnet (context discovery) + haiku (scout template expansion)  
**Output:** `WAI-Spoke/advisors/activation_summary.json` + per-advisor scaffold files

---

## Context

Ozi runs this routine when a new spoke joins the fleet, or when an existing spoke needs a full advisor re-init. The routine is sequential — each advisor runs in priority order so that budget allocation is informed. High-priority advisors (Vera, Archie) claim first; lower-priority advisors receive the remainder.

**Never run advisors in parallel during init.** Parallel budget allocation produces advisor budget wars where every advisor requests max and the total exceeds the fleet budget.

---

## Invocation

```
/wai-ozi-advisor-init --spoke <spoke_id>                  # Full init
/wai-ozi-advisor-init --spoke <spoke_id> --reset          # Clear and re-derive from catalog
/wai-ozi-advisor-init --spoke <spoke_id> --dry-run        # Print activation_summary without writing files
/wai-ozi-advisor-init --spoke <spoke_id> --advisors vera,archie  # Init specific advisors only
```

---

## Step 1 — Discover Spoke Context

Read the following files from the spoke root:
- `CLAUDE.md` — project type, stack, constraints
- `WAI-State.json` — wheel identity, spoke_id, qualifiers
- `WAI-Spoke/WAI-Guide.md` — behavioral protocols (if present)

Produce a `spoke_context` object:

```json
{
  "spoke_id": "<from WAI-State.json wheel.spoke_id>",
  "project_type": "<framework | product | service | data | other>",
  "stack": ["python", "bash"],
  "activation_class": "<all_spoke_types | framework_spokes | product_spokes | service_spokes>",
  "team_size": "<solo | small | large>",
  "goals": "<one-line from identity.success_looks_like>"
}
```

**activation_class rules:**
- `framework_spokes` — project_type = framework
- `product_spokes` — project_type = product
- `service_spokes` — project_type = service or data
- `all_spoke_types` — applies to all; always included

---

## Step 2 — Compute Fleet Budget

Read `hub/WAI-Hub/config/fleet_budget.yaml` (default: 3600 seconds/week total across all advisors).  
If the file does not exist, use `remaining_budget_seconds = 3600`.

```
remaining_budget_seconds = fleet_budget_seconds_per_week
```

---

## Step 3 — Initialize Advisors In Sequence

**Default activation order** (from spec-ozi-advisor-init-routine-v1 `budget_priority_fractions`):

```
vera → archie → expediter → historian → jordy → luci → will → clara → mark → sage
```

For each advisor, execute steps A–G:

### A — Select Scout Templates

Read `hub/WAI-Hub/scout-catalog/{advisor_id}/` for templates matching `spoke_context.activation_class`.  
Each template JSON has an `activation_classes` array — select templates where the array contains the spoke's class or `all_spoke_types`.

If the catalog directory does not exist for this advisor, skip scout template selection (advisor gets empty wishlist).

### B — Customize Prompts

For each selected template, replace placeholders:
- `{{SPOKE_ROOT}}` → absolute path to spoke root (from hub-registry.json)
- `{{SPOKE_ID}}` → spoke_context.spoke_id
- `{{PROJECT_TYPE}}` → spoke_context.project_type
- `{{STACK}}` → comma-joined spoke_context.stack

Write customized scouts to `{spoke_root}/WAI-Spoke/scouts/spoke_local/draft/` with status set to `draft`.

Do not write scouts if `--dry-run` is set.

### C — Negotiate Budget

```python
priority_fraction = budget_priority_fractions[advisor_id]  # from spec
max_claim = remaining_budget_seconds * priority_fraction
requested = min(advisor_default_seconds, max_claim)
granted = min(requested, remaining_budget_seconds)
```

Default `advisor_default_seconds` by advisor:
- vera: 900, archie: 900, expediter: 600, historian: 600, jordy: 300
- luci: 300, will: 300, clara: 300, mark: 300, sage: 300

### D — Write schedule.yaml

Write `{spoke_root}/WAI-Spoke/advisors/{advisor_id}/schedule.yaml`:

```yaml
advisor_id: "<advisor_id>"
version: 1
last_updated: "<ISO-8601 now>"
last_updated_by: "ozi-advisor-init"
enabled: true

cadence:
  interval_minutes: 10080  # weekly
  on_event:
    - post_savepoint
    - post_closeout

run_budget_seconds: <granted_seconds>

time_request:
  current_allocation_seconds: <granted_seconds>
  requested_allocation_seconds: <granted_seconds>
  justification: "Initial allocation — no expeditions run yet"
  findings_last_run: null
  draft_scouts_pending: <count of customized scouts>
  scouts_unreached_last_run: []
  urgency: low
time_grant: null

allowed_models:
  - "haiku"
  - "sonnet"

planned_schedule: []
bespoke_need: null
concerns: []
priorities:
  P1: []
  P2: []
  P3: []
  P4: []
  P5: []
```

Do not overwrite if `schedule.yaml` already exists and `--reset` is not set.

### E — Write coverage_taxonomy.yaml

For each selected scout template, derive dimensions from the template's `dimension_id` field.  
Write `{spoke_root}/WAI-Spoke/advisors/{advisor_id}/coverage_taxonomy.yaml`:

```yaml
advisor_id: "<advisor_id>"
taxonomy_version: "1.0.0"
last_updated: "<ISO-8601 now>"
last_updated_by: "ozi-advisor-init"
coverage_target_score: 0.80
overall_coverage_score: 0.0  # updated after first expedition

dimensions:
  - id: <dimension_id>
    label: "<dimension label>"
    description: "<what gap this dimension detects>"
    priority: <P1-P5>
    target_scouts: <int>
    scouts:
      - { id: <scout_id>, status: draft }
    coverage_score: 0.0
    gap_risk: <low|medium|high>

gap_scouts_needed: []
total_gaps: <count>
total_slots: <sum of target_scouts>
current_covered: 0
```

Do not overwrite if `coverage_taxonomy.yaml` already exists and `--reset` is not set.

### F — Write scout_wishlist.yaml

Derive from the gap_scouts_needed list. Write `{spoke_root}/WAI-Spoke/advisors/{advisor_id}/scout_wishlist.yaml`.

### G — Decrement Budget

```python
remaining_budget_seconds -= granted_seconds
```

---

## Step 4 — Write activation_summary.json

Write `{spoke_root}/WAI-Spoke/advisors/activation_summary.json`:

```json
{
  "spoke_id": "<spoke_id>",
  "initialized_at": "<ISO-8601>",
  "initialized_by": "ozi-advisor-init",
  "spoke_context": { ...spoke_context... },
  "fleet_budget_seconds": 3600,
  "advisors_activated": ["vera", "archie", "historian", ...],
  "total_budget_allocated": <sum of granted>,
  "budget_remaining": <remaining_budget_seconds>,
  "advisor_allocations": {
    "vera":      { "granted_seconds": 900, "scouts_created": 8, "dimensions": 11 },
    "archie":    { "granted_seconds": 900, "scouts_created": 6, "dimensions": 6  },
    "historian": { "granted_seconds": 540, "scouts_created": 0, "dimensions": 0  }
  },
  "dimensions_below_coverage_target": [],
  "p1_gap_risk_high_count": 0
}
```

---

## Step 5 — Surface to Wilbur

If Wilbur is registered in hub-registry.json, deliver a lug to `{wilbur_path}/WAI-Spoke/lugs/incoming/`:

```json
{
  "type": "task",
  "routed_to": "WILBUR",
  "title": "Advisor init complete — <spoke_id> (<N> advisors activated)",
  "perceive": "activation_summary.json written at {spoke_root}/WAI-Spoke/advisors/",
  "payload_path": "{spoke_root}/WAI-Spoke/advisors/activation_summary.json"
}
```

---

## Dry-run Behavior

When `--dry-run` is set:
- Print `spoke_context`, budget allocation table, and per-advisor plan to stdout
- Do NOT write any files (no schedule.yaml, no taxonomy, no scouts, no activation_summary.json)
- Print `[DRY RUN] activation_summary would be written to: {path}`

---

## Eligibility Rules

- Spoke must exist in hub-registry.json (or `--spoke` is a valid local path)
- fleet_budget_seconds must be > 0
- If an advisor already has a `schedule.yaml` and `--reset` is not set, skip that advisor (log: "skipped — already initialized")

---

## Error Handling

- Missing catalog directory for an advisor: log warning, skip scout template step, continue init
- Budget exhausted before all advisors run: remaining advisors get `run_budget_seconds: 60` (minimal keepalive)
- YAML write failure: log error, continue to next advisor, flag in activation_summary `errors` array

---

## Acceptance Test (run after implementation)

```bash
# Dry-run against framework spoke — must produce activation_summary without writing files
python3 -c "
import subprocess, json
result = subprocess.run(
    ['python3', 'tools/ozi_advisor_init.py', '--spoke', 'framework', '--dry-run'],
    capture_output=True, text=True
)
print(result.stdout[:500])
assert 'vera' in result.stdout
assert 'DRY RUN' in result.stdout
print('PASS')
"
```
