# Wilbur — Autonomous Intelligence Loop: Order of Operations + ROI-Gated Optimization

**Version:** 1.0.0
**Created:** 2026-05-25
**Lug:** lug-wilbur-intelligence-loop-v1

## Purpose

Define the order of operations for Wilbur's autonomous intelligence cycle — the loop that runs continuously to improve session quality, detect drift, and surface actionable recommendations. All optimization steps are ROI-gated: Wilbur calculates projected value before acting.

---

## The Loop

Wilbur's intelligence loop runs in three modes:
- **Session-start mode** — fires at wakeup, produces immediate context
- **Background mode** — runs during session gaps, indexes and refines
- **Post-session mode** — runs at closeout, updates indices and scores

---

## 8-Step Order of Operations

Wilbur's core reasoning cycle. Runs for every candidate idea, improvement, or observation Wilbur encounters. Each step gates the next — no step is skipped.

### Step 1 — Discover

**Action:** Pluck ideas, needs, and aspirations from conversation traces, session tracks, and inferences from observed behavior.

| Field | Value |
|-------|-------|
| Inputs | session tracks, conversation history, PathGraph aspiration index |
| Outputs | `candidate_ideas[]`, `inferred_needs[]`, `stated_aspirations[]` |
| Gate | Is this genuinely new, or already captured somewhere? Check PathGraph before adding. |

### Step 2 — Locate

**Action:** Find the home for this idea within the spoke and module structure. Determine ownership: is this Minder, hub, framework, or a new project?

| Field | Value |
|-------|-------|
| Inputs | candidate from step 1, hub-registry.json, spoke module map |
| Outputs | `spoke_id`, `module`, `owner` |
| Gate | Is the home unambiguous? If two modules could own it, flag for Mario. |

### Step 3 — Evaluate

**Action:** Assess execution feasibility. What would it take to build this? What does the execution path look like? What are the risks?

| Field | Value |
|-------|-------|
| Inputs | located idea, TasteGraph risk tolerance, PathGraph prior attempts |
| Outputs | `feasibility_score`, `execution_sketch`, `risk_flags` |
| Gate | Has this been tried before and abandoned? If so, why? Only proceed if the prior failure is understood. |

### Step 4 — Compare to Captured Lugs

**Action:** Search existing lugs for: exact match, near match, or partial coverage. Avoid duplicates. If partial, assess whether a new lug completes the existing one or conflicts with it.

| Field | Value |
|-------|-------|
| Inputs | evaluated idea, `WAI-Spoke/lugs/bytype/` (all lugs) |
| Outputs | `match_result: none\|partial\|exact`, `related_lug_ids[]` |
| Gate | If exact match exists and is open: update it, don't create a new one. |

### Step 5 — Compare to Current Spec

**Action:** Check if this idea aligns with, extends, or conflicts with the current spec lugs for its module. Identify the spec that governs this area.

| Field | Value |
|-------|-------|
| Inputs | evaluated idea, `WAI-SpecIndex.jsonl`, related spec lugs |
| Outputs | `spec_alignment: aligned\|extends\|conflicts`, `spec_id` (if applicable) |
| Gate | If conflict: do not proceed. Flag for Mario — spec conflicts are decisions, not implementations. |

### Step 6 — Verify Robustness

**Action:** Stress-test the idea: edge cases, dependencies, downstream effects. Use GitNexus impact analysis for code-touching changes. Ensure the acceptance criteria would be unambiguously testable.

| Field | Value |
|-------|-------|
| Inputs | idea + spec alignment, GitNexus impact analysis |
| Outputs | `robustness_score`, `edge_cases[]`, `blast_radius` |
| Gate | Impact HIGH or CRITICAL: pause and flag for Mario before proceeding. |

### Step 7 — Accumulate

**Action:** Hold optimization candidates privately. Do not surface until the summed ROI across accumulated optimizations justifies the interruption cost.

| Field | Value |
|-------|-------|
| Inputs | verified idea, existing `optimization-backlog.json` |
| Outputs | `optimization-backlog.json` (updated) |
| Gate | Does the accumulated ROI exceed the interrupt threshold from TasteGraph? If not: keep accumulating. If yes: proceed to step 8. |
| Note | This is the trust-building mechanism. Wilbur does not surface every idea — only ideas whose combined value justifies the ask. |

Track for each accumulating item: `estimated_value`, `confidence`, `time_sensitivity`.

### Step 8 — Propagate + Refine

**Action:** When ROI threshold is met — present the improvement to Mario with full context. Identify all tangential areas where the same improvement should be adopted. Propose a propagation plan that refines all affected areas together.

| Field | Value |
|-------|-------|
| Inputs | justified optimization batch, PathGraph tangential area map |
| Outputs | `improvement_proposal`, `propagation_plan[]`, `tangential_lugs[]` |
| Gate | Mario ratifies the proposal. Wilbur creates the lugs. Ozi executes. |
| Note | Improvements do not ship one at a time. They ship as a coherent wave that improves the whole system, not just one touch point. |

---

## Session Lifecycle Integration

### Session-Start Order of Operations

Runs automatically at wakeup:

1. **TasteGraph query** — Load verified preferences relevant to current session focus. Apply `work_style` and `notification_preferences`. (Cost: negligible)
2. **PathGraph query** — Retrieve top aspirations for the likely focus module. Get current drift level. (Cost: negligible — index read)
3. **Drift assessment** — Compare PathGraph drift report against current lug statuses. Has significant drift increased since last session? (Cost: negligible)
4. **Historian surface** — Generate ephemeral PRD if drift is significant or a new pattern matches. (Cost: low — template fill)
5. **TasteGraph learning check** — Are there inferred preferences awaiting verification? Surface at most 1 per session. (Cost: negligible)
6. **ROI gate check** — Review optimization backlog. Any item with `projected_roi > threshold` AND `cost < budget`? (Cost: negligible — list scan)

### Background Mode (during session)

Runs when the user is not actively prompting (gap > 30s):

1. Index new track events from the current session into PathGraph (incremental)
2. Update aspiration statuses if lugs completed this session
3. Check for new drift — any newly completed lug that fulfills an aspiration?

### Post-Session Mode (at closeout)

1. Final PathGraph update — mark fulfilled aspirations from this session's completed lugs
2. TasteGraph update — if any preferences were verified this session, mark them
3. Update optimization backlog — remove completed items, re-score remaining
4. Write session contribution to Historian's pattern log

---

## ROI Gate

Every optimization action requires a projected ROI score before execution:

```
ROI = (expected_value_improvement × confidence) / estimated_cost
```

### Thresholds

| ROI Range | Action |
|-----------|--------|
| < 1.0 | Skip — cost exceeds expected value |
| 1.0–2.0 | Queue — run in background mode |
| > 2.0 | Run at next session-start |
| > 4.0 | Surface to user immediately |

Cost is measured in: token spend, time-to-value, and attention budget (from TasteGraph `cost_sensitivity` preferences).

### Dynamic Threshold

The interrupt threshold is not fixed. It adjusts based on:

- `TasteGraph.attention_budget` — how much interruption is welcome right now
- `TasteGraph.peak_windows` — time-of-day preference for deep work vs. triage
- `accumulated_value_sum` — the more that has accumulated, the lower the threshold
- `time_sensitivity_flag` — urgent items lower the threshold immediately

### Escalation Bypass

Time-sensitive improvements bypass accumulation entirely and escalate directly to Mario:
- Blocking multiple lugs
- Degrading active user experience
- Security or data integrity concerns

---

## ROI Calculation Inputs

```
ROI = (expected_value_improvement × confidence) / estimated_cost

Where:
  expected_value_improvement = 0–10 (impact on session quality, system coherence, or drift reduction)
  confidence = 0.0–1.0 (how certain is the projected improvement?)
  estimated_cost = 1 (low) | 3 (medium) | 7 (high) (normalized token + attention cost)
```

---

## Optimization Backlog

Wilbur maintains `wilbur/optimization-backlog.json` — a prioritized list of improvement opportunities identified by the intelligence loop. See `wilbur/schemas/optimization-backlog.schema.json` for the full schema.

Each entry carries:

```json
{
  "id": "opt-{slug}-{hex6}",
  "category": "drift_resolution | preference_learning | index_gap | pattern_recognition",
  "description": "What to optimize",
  "estimated_value": 7,
  "confidence": 0.7,
  "time_sensitivity": "none | low | high | urgent",
  "tangential_areas": ["spoke/module strings"],
  "estimated_cost": "low | medium | high",
  "status": "accumulating | ready_to_surface | surfaced | adopted | rejected",
  "discovered_at": "session-id",
  "source": "pathgraph | tastegraph | historian | manual"
}
```

---

## Propagation Plan Format

When ROI threshold is met, Wilbur presents a propagation plan. See `wilbur/docs/propagation-plan-template.md` for the full format.

A propagation plan includes:
- The primary improvement and its justification
- All tangential areas where the same improvement applies
- Rationale for why they should adopt in the same wave
- Proposed lugs for each area (created only after Mario ratifies)

---

## Virtuous Triangle

The intelligence loop creates a virtuous cycle:
- **PathGraph** improves as sessions add more aspiration data → better drift detection
- **TasteGraph** improves as preferences are verified → better optimization targeting
- **Historian** improves as both feed it better context → better session-start surfaces

Each session makes the next session better.

---

## Test Run: Idea Through All 8 Steps

**Idea:** "Minder-web should show PathGraph drift level on the session dashboard"

1. **Discover** — Stated in session-20260524-2304 track event. PathGraph has no matching aspiration. New entry created.
2. **Locate** — Home: minder-web spoke, dashboard module. Owner: Minder. Unambiguous.
3. **Evaluate** — Feasibility: high. Requires PathGraph to expose a drift API endpoint. No prior attempts.
4. **Compare to lugs** — No exact match. `lug-pathgraph-advisor-spec-v1` partially covers drift detection but not the UI surface.
5. **Compare to spec** — `pathgraph-spec.md` covers drift classification. Extends it (UI surface) — aligned.
6. **Verify** — Edge case: drift level not yet computed for a new session. Needs graceful "no data" state. Robustness: acceptable.
7. **Accumulate** — `estimated_value: 6`, `confidence: 0.8`, `time_sensitivity: low`. ROI = (6 × 0.8) / 1 = 4.8. Threshold: 3.0. → Ready to surface.
8. **Propagate** — Surfaced to Mario with propagation plan: minder-web dashboard + any other spoke dashboards that should show drift. Mario ratifies → lugs created.

---

## Constraints

- Never run an optimization that modifies a lug without user approval
- Never surface more than 3 Historian items at session start (attention budget)
- Never queue a background task that costs > 1000 tokens without ROI > 2.0
- TasteGraph changes require explicit verification — inferred preferences never silently applied
- Spec conflicts halt the loop — they are decisions, not implementations
