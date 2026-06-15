# WAI Advisor Schema — Reference
> Fast path: load `wai-advisor-schema-slim.md` first. Load this file only when deep protocol is needed.

**Version:** 1.0.0
**Source of truth:** `WAI-Spoke/advisors/schema/advisor-schema-v1.yaml`
**Skill trigger:** Read this file when authoring, reviewing, or activating a WAI advisor.

---

## 1. Status Lifecycle

```
        ┌─────────────────────────────────────────────────────────┐
        │                                                         │
        ▼                                                         │
  ┌──────────┐    pilot_contract     ┌───────────┐               │
  │   new    │ ──── required ──────► │ piloting  │               │
  └──────────┘                       └─────┬─────┘               │
                                           │                     │
                    ┌──────────────────────┼──────────────────┐  │
                    │                      │                  │  │
                    ▼                      ▼                  ▼  │
             ┌──────────┐         ┌──────────────┐    ┌─────────┤
             │ promoted │         │   refined    │    │ removed │
             └──────────┘         │ (piloting,   │    └─────────┘
                    │             │ iteration++) │
                    │             └──────┬───────┘
                    │                   │  (re-enters piloting
                    │                   │   with updated contract)
                    │                   ▼
                    │             ┌───────────┐
                    │             │ piloting  │ (next iteration)
                    │             └─────┬─────┘
                    │                   │
                    ▼                   ▼
             ┌─────────────────────────────┐
             │          removed            │
             └─────────────────────────────┘
```

**Transition constraints:**

| From      | To        | Requires                                                            |
|-----------|-----------|---------------------------------------------------------------------|
| new       | piloting  | `pilot_contract` block fully populated; one-piloting-slot free      |
| piloting  | promoted  | Evaluation run; `promote_if` criteria met                           |
| piloting  | refined   | Evaluation run; `refine_if` criteria met; `pilot_iteration++`       |
| refined   | piloting  | Updated `pilot_contract` block; one-piloting-slot still free        |
| piloting  | removed   | Evaluation run; `remove_if` criteria met                            |
| promoted  | removed   | Evaluator decision at any time; status_history entry required       |

---

## 2. Pilot Contract — Non-Optional for status >= piloting

The `pilot_contract` block is **required** whenever `status` is `piloting` or `refined`.

**Why this rule exists:** Without a pre-committed hypothesis and explicit decision criteria, pilot evaluation becomes post-hoc rationalization. The evaluator sees outcomes first, then selects metrics that justify their preferred outcome. The contract forces the team to state — before activation — exactly what they expect, how they will measure it, and what result triggers promotion vs removal. This makes "pilot forever" drift visible: if minimum_observations and minimum_time_window have passed but no evaluation has run, that is a governance failure that AdvisorManager can detect and surface.

Promoted advisors should preserve the pilot_contract block as an audit record of what was promised and what was delivered.

---

## 3. One-Piloting-Slot Rule

**Only one advisor per spoke may hold `status: piloting` at any time.**

This constraint exists because:
- Piloting advisors consume evaluation attention from the evaluator.
- Concurrent pilots produce confounded signals — you cannot isolate which advisor is responsible for a KPI change.
- It forces prioritization: if you want to pilot a new advisor, you must first evaluate (and resolve) the current one.

**Enforcement is dual-layer:**

1. **AdvisorManager (runtime):** Before activating a new advisor into piloting status, AdvisorManager queries the registry for any existing `status: piloting` entry on the same spoke. If one exists, activation is blocked with error `PILOT_SLOT_OCCUPIED`.

2. **Database (structural):** A partial unique index in Postgres enforces the constraint at the data layer, making it impossible to bypass AdvisorManager:
   ```sql
   CREATE UNIQUE INDEX uniq_one_pilot_per_wheel
     ON advisor_registry (wheel_id)
     WHERE status = 'piloting';
   ```
   This means even a direct database write cannot create a second piloting advisor on the same spoke.

**Override procedure:** If you must force a second pilot (emergency, framework testing), the activation call accepts a `--force` flag. Forced overrides require:
- A reason string (logged to `lifecycle.jsonl` with `event: pilot_slot_override`)
- The `status_history` of the displaced advisor must be updated to `removed` or `refined` before the force completes
- The override is surfaced in the next wakeup brief as a governance notice

---

## 4. Field Reference Table

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `advisor.id` | string | Yes | Stable kebab-case machine identifier. Never changes after registration. |
| `advisor.name` | string | Yes | Human-readable display name. Title-case. |
| `advisor.version` | semver string | Yes | Semver. Bump on any behavioral change. |
| `advisor.status` | enum | Yes | `new \| piloting \| promoted \| refined \| removed` |
| `advisor.status_history` | list | Yes | Append-only log of status transitions. Each entry: `{status, at, by}`. |
| `advisor.pilot_iteration` | integer | Yes (when piloting/refined) | Starts at 1; increments on each refinement cycle. |
| `advisor.node_scope` | enum | Yes | `spoke \| hub \| both` |
| `advisor.mission` | string (multiline) | Yes | One paragraph. Why this advisor exists. |
| `advisor.principles` | list of strings | Yes (min 2) | Operating commitments. Surfaced with findings. |
| `advisor.inputs_required.data_stores` | list | Yes | Data sources required. At least one non-optional. |
| `advisor.inputs_required.fields_consumed` | list | Yes | Specific fields read. Used for impact analysis. |
| `advisor.access_required.mcps` | list | Yes | MCP tool identifiers needed. Empty list valid. |
| `advisor.access_required.permissions` | list | No | Extra permission scopes beyond default. |
| `advisor.patterns` | list | Yes (min 1) | Detection patterns. Each entry is one sensing unit. |
| `advisor.patterns[].name` | string | Yes | Stable kebab-case pattern identifier. |
| `advisor.patterns[].query_template` | string | Yes | Named query reference. Do not inline SQL. |
| `advisor.patterns[].fires_on` | list of enum | Yes | `wakeup \| mid_session_on_demand \| post_lug_create \| post_commit \| scheduled` |
| `advisor.patterns[].threshold.type` | enum | Yes | `similarity \| count \| ratio \| boolean` |
| `advisor.patterns[].threshold.value` | number or boolean | Yes | Threshold value. Interpretation depends on type. |
| `advisor.patterns[].evolution_risk` | enum | Yes | `low \| medium \| high` — recalibration priority signal. |
| `advisor.patterns[].shadow` | boolean | Yes (explicit) | When true: logs findings without surfacing them. |
| `advisor.outputs` | list of enum | Yes (min 1) | `surface_at_wakeup \| emit_finding_lug \| propose_teaching_candidate \| escalate_to_lead` |
| `advisor.escalation.lead` | string | Yes | Canonical slug of the escalation target. |
| `advisor.escalation.request_method` | enum | Yes | `lug_routed_to_lead \| surface_at_wakeup \| direct_mcp_call` |
| `advisor.pilot_contract` | block | Yes (when piloting/refined) | Hypothesis, KPIs, evaluation rules. See §5. |
| `advisor.lifecycle.self_review_cadence` | enum | Yes | `daily \| weekly \| monthly \| on_demand` |
| `advisor.lifecycle.self_review_inputs` | list | Yes | Data sources for self-review. At least one. |
| `advisor.lifecycle.hypothesis_threshold.recurrence` | integer | Yes | Review cycles before escalating anomaly. |
| `advisor.lifecycle.hypothesis_threshold.confidence_min` | enum | Yes | `low \| medium \| high` |
| `advisor.lifecycle.rollback_path` | string | Yes | How to roll back after a harmful version bump. |
| `advisor.sub_advisors` | list | No | Delegated sub-advisor IDs. Each must be in registry.json. |

---

## 5. Example pilot_contract Block

```yaml
pilot_contract:

  hypothesis: |
    The Historian advisor will identify at least one prior similar session in
    >= 20% of wakeup events within 60 days of activation, and at least 40% of
    surfaced findings will result in user action (acted_on response in the
    findings log).

  kpis:
    - name: redundant_work_session_count
      definition: "Sessions where >50% of work duplicated prior shipped work,
        as measured by cosine similarity (>= 0.82) of track embeddings against
        completed session vectors from the past 90 days."
      baseline_method: "Run advisor in shadow mode for 14 days pre-activation.
        Record average redundant session count per rolling 30-day window."
      target: "Reduction of 15% in redundant_work_session_count over rolling
        30-day window post-activation vs baseline."

    - name: user_acted_on_rate
      definition: "Proportion of surfaced findings where the user response is
        acted_on, measured from findings-log.jsonl feedback entries."
      baseline_method: "No baseline applicable (new metric). Measure from day 1
        of live activation."
      target: "> 40% acted_on rate across all surfaced findings in the
        evaluation window."

  data_required_for_evaluation:
    minimum_observations: 30
    minimum_time_window: "30 days"
    minimum_advisor_fires: 20

  evaluation_trigger: |
    Whichever comes LAST: minimum_observations (30 pattern firings recorded)
    OR minimum_time_window (30 days elapsed). Both conditions must hold before
    the evaluator begins evaluation.

  decision_criteria:
    promote_if: "redundant_work_session_count KPI target met AND
      user_acted_on_rate > 40% across the evaluation window."
    refine_if: "redundant_work_session_count shows > 5% improvement but is
      below the 15% target, OR precision > 60% but recall too low — suggesting
      threshold recalibration will close the gap."
    remove_if: "No movement in redundant_work_session_count after two full
      pilot iterations OR user-dismissed rate > 70% across surfaced findings."

  evaluator: |
    hub_coordinator (or mario if hub_coordinator is unavailable) runs the
    evaluation at trigger. The evaluator must document the outcome in a
    finding lug (type: finding, routed_to: marco) before changing the advisor
    status in registry.json and adding a status_history entry.
```

---

## 6. Shadow Mode

**`shadow: true` on a pattern means:** the pattern evaluates and logs what it would surface, but produces no visible finding for the user.

Shadow log entries are written to `WAI-Spoke/advisors/{id}/findings-log.jsonl` with these fields:

```jsonl
{"ts": "2026-05-24T10:00:00Z", "pattern": "similar_situation_present", "score": 0.91, "surfaced": false, "shadow": true, "would_have_surfaced": true}
```

**Why shadow mode exists:**

A new pattern may have a poorly calibrated threshold or unexpected false-positive sources. Surfacing those findings live creates noise that erodes user trust — once a user dismisses an advisor's findings as low-quality, they stop acting on the good ones too. Shadow mode lets you accumulate a real-world precision/recall sample without any user-visible impact.

**Shadow mode use cases:**

1. **New pattern validation:** Run shadow for 14+ days before going live. Review the shadow log offline. Flip to `shadow: false` only when false-positive rate is acceptable.

2. **Threshold recalibration:** When refining after a pilot, set a new candidate threshold in shadow alongside the live threshold. Compare performance before switching.

3. **Pre-activation baseline:** Required by the pilot contract example above — shadow mode during the pre-activation window establishes the baseline for KPI measurement.

**Flipping shadow off** requires a version bump to the advisor YAML and a status_history entry documenting who approved the change.

`shadow: false` must be set explicitly. Omitting the field is not equivalent — AdvisorManager treats a missing `shadow` field as a schema error and blocks activation.

---

## 7. evolution_risk on Patterns

The `evolution_risk` field on each pattern signals how likely that pattern's precision will degrade as the underlying data changes:

| Value  | Meaning | Self-review action |
|--------|---------|-------------------|
| `low`  | Query uses stable structural data (e.g. lug status counts). Threshold unlikely to drift. | Review quarterly or when schema changes. |
| `medium` | Pattern uses semi-stable data (e.g. session counts, field values that grow). | Review monthly. Flag for recalibration if KPI shows drift. |
| `high` | Pattern uses embeddings, ML scores, or fast-changing domain data. Threshold will drift as data distribution evolves. | Review weekly during pilot. Requires automatic recalibration plan documented in lifecycle block. |

High evolution_risk patterns must include a `recalibration_plan` note in the pattern's `query_template` reference — the named query should document when and how the threshold is recomputed.
