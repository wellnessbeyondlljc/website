# WAI Lug Schema — Reference
> Fast path: load `wai-lug-schema-reference-slim.md` first. Load this file only when deep protocol is needed.

**Companion to `wai-lug-schema.md`.** Contains examples, schemas, and verbose specs. Load on-demand — not loaded at wakeup.

---

## PEV Chain Pattern — Examples

### Chain Structure

| Role | Purpose | Key Fields |
|------|---------|-----------|
| `perceive` | Frames the problem: evidence, conditions, unknowns | `pev_role`, `pev_chain_id`, `evidence[]`, `conditions[]` |
| `execute` | Records intended action or implementation plan | `pev_role`, `pev_chain_id`, `plan`, `target_files[]` |
| `verify` | Defines proof the work is correct | `pev_role`, `pev_chain_id`, `criteria[]`, `verified_at` |

### JSON Example

```json
{"id": "pev-auth-perceive", "type": "work", "pev_role": "perceive", "pev_chain_id": "pev-auth-20260322", "title": "Auth system: problem framing", "evidence": ["Users can bypass 2FA via API"], "conditions": ["Only affects API endpoints, not web UI"]}
{"id": "pev-auth-execute", "type": "work", "pev_role": "execute", "pev_chain_id": "pev-auth-20260322", "title": "Auth system: implementation plan", "plan": "Add 2FA enforcement middleware to API router"}
{"id": "pev-auth-verify", "type": "work", "pev_role": "verify", "pev_chain_id": "pev-auth-20260322", "title": "Auth system: verification criteria", "criteria": ["API requests without valid 2FA token receive 403", "Existing web UI 2FA flow unchanged"]}
```

---

## Canonical Type System — work.kind Example

```json
{"id": "work-fix-auth-20260322", "type": "work", "work": {"kind": "bug"}, "title": "Fix auth bypass in API middleware"}
```

---

## Vibe Affinity — ROI Scoring Reference

**Vibe categories** for Ozi work queue tiebreaking. When two items have similar ROI, the user's current vibe reshapes ordering:

| Vibe | Energy | Best for | Suppresses |
|------|--------|----------|------------|
| `build` | Creative, generative | Features, epics, new code | Bugs, signal routing |
| `fix` | Focused, corrective | Bugs, reliability, debt | Epics, features |
| `think` | Reflective, strategic | Architecture, signals, decisions | Mechanical tasks |
| `grind` | Steady, mechanical | Batch tasks, thrift, routing | Creative design |
| `ship` | Closing, finishing | In-progress items, close lugs | Starting new work |

**ROI formula:** `(impact × leverage) / effort`
- `impact`: 1-10 (from lug field, or inferred from type)
- `leverage`: 1.0-2.0 (1.0 standalone, 1.3 in-progress momentum, 1.5 foundational/unblocking)
- `effort`: 1-5 (from lug field, or inferred from type)
- Signals capped at ROI 5.0 (routing chores, not implementation)

**Vibe multipliers** (applied to base ROI):

| Type | build | fix | think | grind | ship |
|------|-------|-----|-------|-------|------|
| feature | 1.6x | 0.7x | 1.2x | 0.6x | 1.1x |
| bug | 0.6x | 1.8x | 0.6x | 1.1x | 1.2x |
| task | 1.0x | 1.1x | 0.7x | 1.4x | 1.1x |
| epic | 1.3x | 0.6x | 1.6x | 0.5x | 0.7x |
| signal | 0.5x | 0.8x | 1.3x | 1.2x | 0.6x |
| other | 0.8x | 0.9x | 1.1x | 1.3x | 0.9x |
| in_progress (ship only) | — | — | — | — | 1.8x |

**Urgency tiers** (sort before ROI — all tier-1 before any tier-2):

| Value | Band | Meaning |
|-------|------|---------|
| 1 | URGENT | Immediate — bypasses scheduled windows |
| 2 | HIGH | Before normal queue |
| 3 | NORMAL | Default (omitting urgency = tier 3) |
| 4 | LOW | After normal queue |
| 5 | DEFER | Process last |

Sort key: `(urgency asc, ROI desc)`. An urgency=1 lug with ROI 2.0 dispatches before an urgency=3 lug with ROI 10.0.

**Scorer tool:** `tools/score_backlog.py [vibe]`

### Example

```json
{"i": "bug-auth-timeout", "ty": "bug", "t": "Fix auth timeout in API", "impact": 7, "effort": 2, "va": "fix"}
```
Base ROI = (7 × 1.0) / 2 = 3.5. With `fix` vibe: 3.5 × 1.8 = 6.3. With `build` vibe: 3.5 × 0.6 = 2.1.

---

## Lug ID Generation — Extended Example

```
sha256("Fix authentication timeout") = 4f1e687a652f...
i = "4f1e687a652f"
```

---

## Lug Creation Template

```json
{
  "i": "4f1e687a652f",
  "ty": "task",
  "t": "Fix authentication timeout in session middleware",
  "s": "o",
  "ca": "2026-02-28T10:00:00Z",
  "gb": "claude-sonnet-4-6",
  "description": "Session timeout not being refreshed on user activity. Token expires even when user is active.",
  "priority": "medium",
  "impact": 5,
  "tags": ["auth", "session"],
  "blocks": [],
  "blocked_by": [],
  "perceive": "Read src/middleware/session.js — timeout logic at line ~45. Read WAI-Spoke/WAI-State.json for current session config.",
  "execute": "Update session middleware to refresh token on any authenticated request. Add 15-minute sliding window.",
  "verify": "curl -H 'Authorization: Bearer {token}' /api/ping — token should refresh. Wait 10 minutes, repeat — should still be valid."
}
```

Write to `WAI-Spoke/lugs/bytype/{type}/open/{id}.json` (one JSON file per lug).

---

## `implementation` Lug — Full JSON Schema

```json
{
  "ready_to_build_gate": {
    "required": true,
    "checks": [
      "Scope is bounded and non-goals are explicit",
      "Dependencies, blockers, and target files are named",
      "Sequence is clear enough to execute without chat context",
      "Verification requirements are concrete and relevant",
      "Review sources and review questions are present"
    ]
  },
  "review_rubric": {
    "self_review_required": true,
    "ready_to_build": [
      "Is this lug mature enough to build without filling architectural gaps from chat?",
      "Are sequence, non-goals, and dependencies explicit?",
      "Are target files or target objects named?",
      "Is verification concrete rather than aspirational?"
    ],
    "acceptance_checks": [
      {
        "id": "scope",
        "question": "Did the implementation stay within the lug's scope and non-goals?",
        "pass_condition": "No unauthorized file or architecture expansion occurred",
        "failure_action": "Move to in_remediation and add review note"
      },
      {
        "id": "canonical_alignment",
        "question": "Do the changes align with the goal-state design and parent epic?",
        "pass_condition": "No contradiction with the canonical object model or behavior remains in touched files",
        "failure_action": "Move to in_remediation and add review note"
      },
      {
        "id": "persistence",
        "question": "Was review, progress, and completion written back to the lug?",
        "pass_condition": "The implementation lug and session-summary reflect the real work performed",
        "failure_action": "Treat work as incomplete until persisted"
      },
      {
        "id": "verification",
        "question": "Was actual verification performed and recorded?",
        "pass_condition": "Claims are backed by concrete checks, not just assertions",
        "failure_action": "Require remediation or downgrade completion claim"
      },
      {
        "id": "handoff_quality",
        "question": "Could a new agent continue from the lug alone?",
        "pass_condition": "Next steps, blockers, observations, and remaining work are durable",
        "failure_action": "Require lug update before acceptance"
      }
    ]
  },
  "remediation_plan": {
    "required_when_in_remediation": true,
    "version": 1,
    "authored_at": "ISO-8601",
    "authored_by": "agent-name",
    "model": "model-id",
    "addresses_note_ids": ["rn-001-example"],
    "problem_summary": "Why the prior attempt failed or was kicked back.",
    "planned_changes": [
      "What will be changed to address the review note",
      "What will remain out of scope during remediation"
    ],
    "verification_plan": [
      "How the remediation will be checked",
      "What evidence will be gathered before recheck"
    ],
    "risks": ["Known uncertainty, dependency, or likely follow-up"],
    "needs_user_review": false
  },
  "workflow": {
    "current_phase": "plan|work|verify|accept",
    "current_owner": "planner|builder|validator|user",
    "current_state": "open|in_progress|complete",
    "handoff_reason": "Why the ball moved to this owner",
    "next_expected_transition": "What should happen next",
    "steps": {
      "plan": {"type": "plan", "owner": "planner", "state": "open|in_progress|complete"},
      "work": {"type": "work", "owner": "builder", "state": "open|in_progress|complete"},
      "verify": {"type": "verify", "owner": "validator", "state": "open|in_progress|complete"},
      "accept": {"type": "accept", "owner": "user", "state": "open|in_progress|complete"}
    }
  },
  "review_notes": [
    {
      "id": "rn-001-example",
      "at": "2026-03-19T09:05:00Z",
      "by": "agent-name",
      "model": "claude-sonnet-4-6",
      "type": "concern|gap|suggestion|acceptance-note|blocked",
      "scope": "signals|tracks|state|verification|etc",
      "message": "Detailed description of issue",
      "file_refs": ["path/to/file.md:123"],
      "status": "open|acknowledged|resolved|rejected",
      "resolution_note": "How this was addressed"
    }
  ],
  "review_cycles": [
    {
      "cycle": 1,
      "reviewed_at": "2026-03-19T09:05:00Z",
      "reviewed_by": "agent-name",
      "model": "claude-sonnet-4-6",
      "result": "approved|needs_remediation|accepted",
      "summary": "Brief review outcome description",
      "blocking_note_ids": ["rn-001-example"],
      "non_blocking_note_ids": []
    }
  ],
  "acceptance": {
    "status": "pending|ready_for_acceptance|accepted",
    "accepted_at": null,
    "accepted_by": null,
    "model": null,
    "notes": "Final acceptance notes"
  }
}
```

**Recommended fields** (in addition to standard lug fields): `parent_epic`, `composes`, `target_files`, `non_goals`, `sequence`, `implementer_review`, `subagent_policy`, `verification_requirements`, `implementation_feedback`, `ownership`.

---

## Victory Briefing Format

After a lug or epic is implemented and verified, present a Victory Briefing to the user.

### Format

1. **Header:** `### EPIC WIN: {Title}` or `### LUG CLOSED: {Title}`
2. **The Human Why:** 1-2 paragraphs explaining what was built and *why it matters*. Focus on value, not code.
3. **The Stats:**
   - **Complexity:** Low | Medium | High
   - **Impact:** 1-10
   - **Files Touched:** count
   - **Verification:** brief summary of tests passed
4. **The "Check it Out":** A specific command or file the user can inspect.

---

## WAI-Challenges.jsonl

First-class append-only file for stable problem statements, independent of hypotheses (idea lugs) that address them.

### Schema

```json
{
  "i": "chal-{3-5-word-slug}",
  "ty": "challenge",
  "statement": "The stable problem text — refined after wai-improve Step 3",
  "first_seen": "ISO-8601",
  "first_seen_in": "idea lug ID of the first idea that identified this challenge",
  "status": "open | resolved | deferred",
  "related_lugs": ["idea and epic IDs addressing this challenge"],
  "resolution_notes": "How it was resolved (if status=resolved)"
}
```

**Append-only:** Latest entry per `i` wins.

**Lifecycle:** Created by `/wai-improve` Step 3b on first intake of a challenge. Updated each time a new idea links to it.

**Relationship to ideas:** Challenge = stable problem. Idea = one hypothesis. One challenge can have many ideas across sessions and models. The `challenge_id` field on an idea lug is the link back.

**Slug generation:** Take 3–5 meaningful words (nouns, verbs — skip stopwords), join with hyphens, lowercase.
Example: `"Recurring friction across sessions is invisible"` → `chal-recurring-friction-invisible`

---

## AI Workflow with Lugs

1. **Wakeup** — Browse open lugs (s=o, s=p) to understand priorities
2. **Session** — Create lugs for sub-tasks or newly discovered bugs
3. **Autosave** — Checkpoint lugs with `ty: "autosave"` and `reconciled: false`
4. **Closeout** — Reconcile autosaves, signal high-impact items, update status

---

## Cross-Spoke Authoring — Full JSON Example

```json
{
  "_behavior_directive": {
    "what_this_is": "A work item to be ADDED to the task tracker",
    "what_this_is_NOT": "An instruction to execute immediately",
    "processing_agent": "incoming router appends to lugs/bytype/task/open/",
    "expected_outcome": "Item appears in task list for user to prioritize"
  },
  "ty": "task",
  "source_wheel_id": "framework",
  "destination_wheel_id": "basher",
  "t": "Fix authentication timeout in session middleware",
  "ca": "2026-02-28T10:00:00Z"
}
```

---

## Ozi Gardening Lug Types

Ozi automation history lives in these lug types — **not** in WAI-State.json.

### ozi-controller

One Ozi automation pass or bounded task batch.

| Field | Value |
|-------|-------|
| `id` | `ozi-ctrl-{YYYYMMDD-HHMM}-{task-slug}` |
| `type` | `"ozi-controller"` |
| `title` | What Ozi is orchestrating |
| `session_id` | Session that created this controller |
| `target_lug_id` | Implementation or task lug being worked |
| `status` | `active \| completed \| failed` |
| `work_lug_ids` | Child ozi-work lug ids |
| `test_lug_ids` | Paired ozi-test lug ids |
| `created_at` | ISO-8601 |
| `completed_at` | ISO-8601 or null |

### ozi-work

One discrete unit of work dispatched by an Ozi controller.

| Field | Value |
|-------|-------|
| `id` | `ozi-work-{YYYYMMDD-HHMM}-{task-slug}` |
| `type` | `"ozi-work"` |
| `controller_id` | Parent ozi-controller lug id |
| `task` | Concise description of what was done |
| `target_file` | File or resource modified |
| `status` | `completed \| failed \| skipped` |
| `result` | Short outcome note |
| `created_at` | ISO-8601 |
| `completed_at` | ISO-8601 or null |

### ozi-test

Paired verification record. Required before any ozi-work lug can move to `ready_for_recheck`.

| Field | Value |
|-------|-------|
| `id` | `ozi-test-{YYYYMMDD-HHMM}-{task-slug}` |
| `type` | `"ozi-test"` |
| `work_lug_id` | Parent ozi-work lug id |
| `test_command` | Runnable shell or Python verification command |
| `expected` | Expected output or behaviour |
| `actual` | Observed result |
| `result` | `pass \| fail \| skip` |
| `tested_at` | ISO-8601 |

**Rule:** Every ozi-work lug must have a paired ozi-test lug.

---

## Execute-When Gates — JSON Schemas

### execute_when Schema
```json
{
  "execute_when": {
    "all_completed": ["lug-id-1", "lug-id-2"],
    "any_completed": ["lug-id-3"],
    "phase_completed": "p1-foundation",
    "manual_gate": false
  }
}
```

### Phase Definitions in WAI-State.json
```json
{
  "_work_queue": {
    "phases": [
      {"id": "p1-foundation", "title": "Foundation fixes", "order": 1},
      {"id": "p2-orchestration", "title": "Queue orchestration", "order": 2}
    ]
  }
}
```

---

## Routing Fields — JSON Example and Test Case

### scope_verified_by Example
```json
{
  "routed_to": "FRAMEWORK",
  "scope_verified_by": "user (Session 74: 'this is a wakeup protocol fix affecting all spokes')"
}
```

### Routing Decision Test Case

User requests "optimize wakeup for fast projects":
- Ozi recognizes this improves wakeup (framework concern)
- Routes to: `epic-minimal-context-wakeup-v1` (LOCAL) + `signal-ozi-routing-awareness` (SIGNAL)
- Announces: "Creating epic → LOCAL + Creating signal → SIGNAL (all spokes learn from this)"

---

## Anti-Pattern Examples

### Ambiguous action (bad)
```json
{"action": "implement_feature"}
```

### Explicit intent (good)
```json
{"request_type": "work_item_tracking", "work_description": "Add caching layer to API", "do_not_execute_automatically": true}
```

### Implicit context (bad)
```json
{"task": "Update the config"}
```

### Self-contained (good)
```json
{"task_type": "configuration_change", "target_file": "WAI-Spoke/WAI-State.json", "change_description": "Add hub_analysis section with spoke_count and last_sync fields", "tracking_only": true}
```

---

## Advisor Data Source Autonomy

Each advisor declares its data sources in scan_state.json:

```json
{
  "data_sources": [
    {
      "source": "path/to/data",
      "fields_used": ["field1", "field2"],
      "fields_needed": ["field3"],
      "adequacy": "good|partial|missing"
    }
]
}
```

**Adequacy check at activation:** When an advisor activates, it checks each data source:
- `good`: source exists, all needed fields present
- `partial`: source exists but missing fields → create gap lug
- `missing`: source not found → create gap lug with higher priority

**Gap lug template:**
```json
{"ty": "task", "t": "Advisor {name} needs {field} in {source}", "rt": "LOCAL", "gb": "advisor-{name}"}
```

Gap lugs are routed to the team responsible for the data source.

---

Refer to `wai-lug-schema.md` for newly added Crew Fields (state, risk_tier, lead_advisor, consulting_advisors, execution_mode, model_override).