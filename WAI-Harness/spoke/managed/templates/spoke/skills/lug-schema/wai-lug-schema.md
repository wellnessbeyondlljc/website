# WAI Lug Schema

**Lug System Protocol — task graph management, schemas, authoring, and lifecycle.**

---

## Execution Context

- **Nodes:** spoke, hub
- **Exposure:** spoke.chat:local, spoke.chat:external

---

## Canonical Storage

**Single source of truth:** This file is the canonical declaration for lug storage. All other protocol files defer here.

**Folder hierarchy:**
```
WAI-Spoke/lugs/
  incoming/                        — inbound deliveries (operational)
  outgoing/                        — outbound deliveries (operational)
  bytype/
    epic/{open,in_progress,completed}/
    task/{open,in_progress,completed}/
    feature/{open,in_progress,completed}/
    bug/{open,in_progress,completed}/
    implementation/{in_progress,completed}/
    session-summary/               — all completed, no status subfolder
    other/{open,completed}/        — rare types (idea, policy, learning, etc.)
```

| What | Where | Notes |
|------|-------|-------|
| Active lugs | `lugs/bytype/*/open/` and `bytype/*/in_progress/` | Scanned at wakeup |
| Completed lugs | `lugs/bytype/{type}/completed/` | One file per lug |
| Signals (v2) | `WAI-Spoke/signals/{inbound,processed}/` + `signals/registry.json` | Signal lugs use `routed_to: "FRAMEWORK"` — spokes never receive raw signals |
| Lug index | `WAI-Spoke/WAI-LugIndex.jsonl` | Lightweight lookup — on-demand only |
| Incoming/outgoing | `WAI-Spoke/lugs/incoming/` and `outgoing/` | Delivery channel only |
| Hub bulletin | `WAI-Hub/signals/incoming/` | High-impact lugs copied here at closeout |
| Reference docs | `WAI-Spoke/reference/` | Top-level, peer to lugs/sessions/skills |

**Storage rules:**
- **New lugs** → write to `lugs/bytype/{type}/open/{id}.json`
- **In-progress** → move to `lugs/bytype/{type}/in_progress/{id}.json`
- **Completed** → move to `lugs/bytype/{type}/completed/{id}.json`
- **Index** → regenerated at closeout
- **Wakeup** → scans `bytype/*/open/` and `bytype/*/in_progress/` only

`WAI-Spoke/WAI-Signals.jsonl`, `WAI-Spoke/WAI-Lugs.jsonl`, and `WAI-Spoke/lugs/active/` are all **retired**. Do not create or write to any of them.

---

## What Is A Lug

A lug is a JSON file at `WAI-Spoke/lugs/bytype/{type}/{status}/{id}.json`. The folder path tells you what it is and whether it needs attention. Lugs are the persistent memory of the session system — they carry work items, decisions, signals, and protocols across sessions, models, and projects.

**Lugs travel across contexts.** They must be unambiguous enough that ANY agent can interpret them correctly WITHOUT your current conversation history.

---

## Key Mapping (Minified ↔ Full)

| Short | Full | Purpose |
|-------|------|---------|
| `i` | `id` | Unique identifier |
| `t` | `title` | **Indicative, descriptive title (5+ words)**. Explain the *intent* or *impact*. |
| `ty` | `type` | Lug type (see catalog below) |
| `s` | `status` | Current status |
| `ca` | `created_at` | ISO-8601 creation timestamp |
| `gb` | `gathered_by` | Agent or session that created it |
| `v` | `version` | Version number (foundation, core-protocol lugs) |
| `fw_ver` | `fw_ver` | **Framework version when lug was authored** (e.g. "3.0.0"). Set once at creation — never updated. Enables currency scoring. See `wai-lug-compat.md`. |
| `va` | `vibe_affinity` | **Work energy category** — one of: `build`, `fix`, `think`, `grind`, `ship`. Optional. Used by Ozi ROI scorer for tiebreaking when items have similar priority. |
| `impact` | `impact` | **Impact score** 1-10. Used by ROI scorer. Default inferred from type if absent. |
| `effort` | `effort` | **Effort score** 1-5. Used by ROI scorer. Default inferred from type if absent. |
| `rt` | `routed_to` | Routing target: `LOCAL`, `FRAMEWORK`, or `SPOKE/{spoke_id}` for cross-spoke. Signal-type lugs use `"FRAMEWORK"` |

**Title Policy:**
- **No generic session summaries:** "Session 35 summary" is BANNED.
- **Good:** "Session 35: Successfully implemented chat-to-track epic and historian dual-watermark"
- **Bad:** "Task: Update state"

Both short and full key forms are valid. Prefer short keys for storage efficiency.

---

## Status Values

| Code | Meaning |
|------|---------|
| `o` or `open` | Open / pending — not started |
| `p` or `in-progress` | In progress — actively being worked |
| `c` or `closed` or `resolved` | Complete / closed |
| `b` or `blocked` | Blocked by another lug or external dependency |

---

## Complete Lug Type Catalog

| Type | Purpose | Auto-process? |
|------|---------|--------------|
| `task` | Work item to track and implement | No — add to tracker |
| `bug` | Defect requiring a fix | No — add to tracker |
| `feature` | New capability or enhancement | No — add to tracker |
| `review` | Something needing review or verification | No — add to tracker |
| `epic` | Large multi-session effort (blocked until tasks clear) | No — add to tracker |
| `implementation` | Execution-control lug for non-trivial planned work | No — add to tracker |
| `signal` | Patch-now alert (impact >= 8) — `routed_to: "FRAMEWORK"` | No — write to `WAI-Spoke/signals/inbound/` |
| `foundation` | Project identity, boundaries, approach | No — defines the project |
| `session-summary` | Completed session record (autosaves reconciled) | No — archive only |
| `autosave` | Crash-recovery checkpoint from mid-session | Reconcile at closeout |
| `policy` | Project rules or constraints | No — reference document |
| `observation` | Factual observation logged for pattern detection | No — record |
| `learning` | Cross-session insight worth preserving | No — record |
| `maintenance` | Infrastructure or tooling work | No — add to tracker |
| `core-protocol` | Framework protocol documentation | No — reference document |
| `delivery_confirmation` | Confirms lug was delivered to target spoke | Auto-acknowledged |
| `phone-home` | Hub requests status report from spoke | Auto-handled by learn |
| `config` | Configuration update for node | Applied during learn |
| `session` | Historical session record (legacy) | No — archive only |
| `challenge` | Problem-centric anchor for idea lugs | No — append-only in WAI-Challenges.jsonl |

---

## PEV Chain Pattern

For work requiring structured perceive→execute→verify reasoning, use linked lugs instead of PEV fields on a single record.

Each lug in a PEV chain carries:
- `pev_role`: one of `perceive` | `execute` | `verify`
- `pev_chain_id`: shared identifier for the chain (e.g. `pev-feature-auth-20260322`)

**When to use:** Architectural decisions, bug investigations, features with clear acceptance criteria.
**Skip for:** Simple tasks, signal lugs, session summaries.

**Compatibility:** Existing lugs with `perceive`/`execute`/`verify` as plain fields remain valid. New structured work should prefer the chain pattern.

See `wai-lug-schema-reference.md` for chain structure table and JSON examples.

---

## Canonical Type System

### Top-Level Types (use these for new lugs)

| Type | Purpose |
|------|---------|
| `epic` | Large work body spanning multiple sessions |
| `work` | Executable work item (replaces task/bug/feature) |
| `decision` | Architectural or directional choice |
| `finding` | Investigation result or discovered fact |
| `test` | Test specification or result |
| `session-summary` | End-of-session record |
| `signal` | Patch-now alert (impact >= 8) — routes to framework only (`routed_to: "FRAMEWORK"`) |

### work.kind Field

When creating a `work` lug, set `work.kind` to classify the work:

| work.kind | Replaces | Use when |
|-----------|---------|---------|
| `task` | type: "task" | Defined unit of work |
| `bug` | type: "bug" | Defect or broken behavior |
| `feature` | type: "feature" | New capability |
| `implementation` | type: "implementation" | Capability rollout |

**Dual-Read Compatibility:** Existing lugs with `type: "task"`, `type: "bug"`, or `type: "feature"` remain valid. Do not bulk-rewrite. New lugs should use canonical types. Treat `type: "task"` as equivalent to `type: "work", work.kind: "task"`.

---

## Lug ID Generation

Generate `i` from first 12 characters of SHA256 of the title:
```
i = sha256(title)[:12]
```

For named lugs (foundation, epic): use human-readable IDs:
```
"lug-fnd-abc12345"        (foundation)
"epic-slimdown-20260227"  (epic with date)
"ss-e48218a6"             (session-summary)
```

---

## Required Field Defaults

| Field | Default | Notes |
|-------|---------|-------|
| `s` | `"o"` | Open — not started |
| `ca` | current UTC timestamp | ISO-8601, e.g. `"2026-03-17T04:44:00Z"` |
| `impact` | `5` | Medium. Adjust up/down based on scope. |
| `priority` | `"medium"` | Use `"before_next_epic"` only when truly blocking |
| `blocks` | `[]` | Empty array |
| `blocked_by` | `[]` | Empty array — evaluated by dispatch (items with unresolved blockers are skipped) |
| `tags` | `[]` | Empty array |
| `phase` | `null` | Phase membership ID (e.g. `"p1-foundation"`) — groups items for milestone tracking |
| `phase_order` | `null` | Numeric ordering within a phase (lower = earlier) |
| `execute_when` | `null` | Conditional trigger — see Execute-When Gates section below |

### `gb` (gathered_by) — Model ID Required

`gb` MUST be the **actual model identifier** of the AI that authored the lug.

```
CORRECT:  "gb": "claude-sonnet-4-6"
CORRECT:  "gb": "claude-opus-4-6"
CORRECT:  "gb": "gemini-1.5-pro"
WRONG:    "gb": "Sparky"
WRONG:    "gb": "Assistant"
WRONG:    "gb": "AI"
```

**Why this matters:** Self-chosen names create ambiguity. `gb` is an audit field — it must answer "which model wrote this?" unambiguously across sessions, tools, and time. If working in a v1 spoke with `current_ai: "Sparky"` in WAI-State.json, ignore that field — use your model ID.

Optionally append session ID for traceability: `"gb": "claude-sonnet-4-6 (session-20260317-0444)"`

---

## Execute-When Gates

Conditions that must be true before a lug becomes dispatchable. Evaluated by `score_backlog.py`, `wai_ozi.py`, and `wai-chain.sh`.

| Field | Logic | Purpose |
|-------|-------|---------|
| `all_completed` | AND | Every listed lug ID must be in `completed/` or `delivered/` |
| `any_completed` | OR | At least one listed lug ID must be completed |
| `phase_completed` | GROUP | All lugs declaring that `phase` value must be completed |
| `manual_gate` | BLOCK | If `true`, always blocked until user explicitly overrides |

All conditions must be satisfied. Missing conditions are ignored (permissive).

`execute_when.all_completed` subsumes `blocked_by` for new lugs. Existing `blocked_by` arrays remain valid — the evaluator checks both.

Phase membership: set `"phase": "p1-foundation"` on a lug. Phase definitions live in `WAI-State.json _work_queue.phases`. Gated items appear as "gated" in `score_backlog.py` output.

See `wai-lug-schema-reference.md` for JSON schema and phase definition example.

---

## PEV Fields (Required for Actionable Lugs)

**Every `task`, `epic`, `bug`, `feature`, `review`, and `implementation` lug MUST include PEV fields.**

| Field | Purpose |
|-------|---------|
| `perceive` | What to read/examine before starting. File paths, current state, context. |
| `execute` | Concrete steps to take. What to build, modify, or design. |
| `verify` | How to confirm the work is done correctly. |

**Why this matters:** A lug without PEV forces the next agent to explore the codebase guessing where to start. PEV gives them a runway — `perceive` orients, `execute` directs, `verify` closes the loop.

See `wai-lug-schema-reference.md` for a full PEV lug example.

---

## `implementation` Lugs

`implementation` is a first-class lug type for **non-trivial execution batches**.

Use an `implementation` lug when:
- work spans multiple files or multiple child lugs
- work sits under an `epic` and needs ordered execution
- the implementer needs a review gate before editing
- multiple agents or sub-agents may participate
- you want durable implementation feedback, not just a one-shot task description

**Default expectation:** If work is non-trivial and epic-backed, create an `implementation` lug.

**Canonical Lifecycle:**
```
planned → review_pending → approved_to_implement → in_progress → in_remediation → ready_for_recheck → implemented → accepted
```

**Review Gate Rules:**
1. **Pre-Implementation Review**: Before any implementation, create review cycle documenting approval/concerns
2. **Persistent Review Notes**: All findings must be recorded as `review_notes[]`, not just in chat
3. **Remediation Tracking**: If review finds gaps, status → `in_remediation` with blocking note IDs
4. **Recheck Required**: After fixes, move to `ready_for_recheck`; reviewer confirms resolution
5. **Final Acceptance**: Only after all review notes resolved can status move to `accepted`
6. **Lug-Centered Interaction**: reviewer/implementer back-and-forth written to the lug; chat tells agents which lug to load
7. **Ready-To-Build Gate**: Check `ready_to_build_gate` criteria before implementation starts
8. **Self-Grading Requirement**: Run `review_rubric.acceptance_checks` against own work before requesting recheck
9. **Remediation Plan Requirement**: If kicked to `in_remediation`, write `remediation_plan` before retrying
10. **Workflow Action Tracker**: Update `workflow.current_phase/owner/state` at major handoffs

**Persistence Gate:** Review is not complete until written back to the lug. Update lug with review cycle entry before editing any target file.

**Completion Gate:** Implementation not complete until lug is updated with: what changed, verification performed, contributors, completion notes, observations, follow-up candidates.

**Remediation Rule:** In `in_remediation`, persist a `remediation_plan` first. If scope changes materially, set `needs_user_review: true` before implementing.

**Sub-agent Rule:** Sub-agents may assist with bounded analysis or verification but do not replace the primary implementer's architectural judgment unless the lug explicitly allows it.

See `wai-lug-schema-reference.md` for full `implementation` JSON schema (ready_to_build_gate, review_rubric, remediation_plan, workflow, review_notes, review_cycles, acceptance).

---

## Lug Lifecycle

```
CREATE → DOGFOOD → DISCUSS → IMPLEMENT → VERIFY → CELEBRATE → ARCHIVE
```

1. **CREATE** — Write to `lugs/bytype/{type}/open/{id}.json` with `s: "o"`. Ensure PEV fields are present.
2. **DOGFOOD** — Run the naive agent test. Fix gaps before work begins.
3. **DISCUSS** — (Optional) For high-impact lugs (impact >= 8), present strategy to user and refine.
4. **IMPLEMENT** — Set `s: "p"`. Follow the `execute` steps. If reality diverges, update the lug first.
5. **VERIFY** — Execute every `verify` step. No `TODO` or `FIXME` remaining.
6. **CELEBRATE** — Present the Victory Briefing. Set `s: "c"`.
7. **ARCHIVE** — Move to `completed/`. Index regenerated at closeout.

---

## Dogfooding Lugs (Naive Agent Test)

**Before finalizing any lug intended for another agent (including future-you), validate it:**

1. **State what you'll test** — which lug(s), what aspects.
2. **Invoke the Naive Agent Test** — Send `perceive`, `execute`, and `verify` to a sub-agent with **zero project context**.
3. **Analyze the Plan** — Ask the sub-agent to draft an implementation plan based only on the lug.
4. **Identify "STUCK" Points** — Anywhere the sub-agent needs clarification is a gap.
5. **Fix Gaps** — Update the lug with missing file paths, specific line numbers, or clearer logic.

**The Golden Rule:** A lug is only `dogfood_pass: true` when a "cold" agent can implement it correctly without asking a single question.

---

## Implementation & Verification Protocol

When implementing a lug:
- **Set Focus:** Declare the lug ID you are working on.
- **Follow PEV:** Do not improvise. If `execute` steps are wrong, backtrack to Discuss and update the lug.
- **Surgical Edits:** Keep changes focused on the lug's goals. Avoid unrelated refactoring.
- **Mandatory Verification:** Run all commands in `verify`. If none specified, invent and run a test that proves behavioral correctness.

---

## Cross-Spoke Authoring (Critical Safety)

When creating lugs that travel to other nodes, ALWAYS include `_behavior_directive` (see `wai-lug-schema-reference.md` for example).

**The misinterpretation test** — before sending any lug, ask:
1. Could a different model read this and execute it immediately?
2. Could this be interpreted as "do now" vs "track for later"?
3. Are there implicit assumptions not stated?
4. Would I understand this with zero context?

If any answer is "yes or maybe" → add more clarity.

**Cross-spoke checklist:**
- [ ] `_behavior_directive` present and complete
- [ ] `what_this_is_NOT` explicitly prevents misinterpretation
- [ ] `source_wheel_id` and `destination_wheel_id` set
- [ ] Content is self-contained (no "see above" references)
- [ ] Action words are qualified ("TRACK this" not just "implement")

See `wai-lug-schema-reference.md` for full cross-spoke JSON example.

---

## Priority Flags

| Value | Meaning |
|-------|---------|
| `"P1"` | High — urgent, blocking, or critical path |
| `"P2"` | Medium — important, scheduled work |
| `"P3"` | Low — backlog, non-blocking |
| `"P4"` | Trivial — nice-to-have, no deadline |

**Migration:** `"high"` or `"critical"` = P1; `"medium"` = P2; `"low"` = P3. No bulk rewrite. New lugs MUST use P1–P4.

**Workflow qualifiers** (store in `workflow_flag`, not `priority`):

| Value | Meaning |
|-------|---------|
| `"before_next_epic"` | Must clear before any new epic starts |
| `"session_focus"` | Primary focus of the current session |

If found in `priority` on an existing lug, treat as P1-equivalent.

---

## Scope Flags

- `"only_this_spoke"` — Applies to this project only
- `"all_spokes"` — Applies to all projects of this type
- `"wheel"` — Applies globally (hub + all spokes)

---

## Routing Fields (Lug Dispatch Awareness)

**When creating a lug, declare its routing destination to enable scope-aware dispatch.**

### `routed_to` (Enum, Required for all lugs)

| Value | Meaning | Behavior at Closeout |
|-------|---------|---------------------|
| `"LOCAL"` | Stays in this spoke | `completed/` only |
| `"FRAMEWORK"` | Framework improvement | hub teaching delivery + `completed/` |
| `"SIGNAL"` | **Deprecated** — use `"FRAMEWORK"` for signal-type lugs | treated as FRAMEWORK; do not use |
| `"SPOKE/{spoke_id}"` | Cross-spoke routing | `{hub_path}/WAI-Hub/lugs/incoming/{spoke_id}/` + completed locally |

**Default:** If not set, assume `LOCAL`. Ozi should confirm routing before creating.

### `scope_verified_by` (Required if routed_to != LOCAL)

`"user"` | `"ozi"` | `"framework"` | `"auto-signal"` — who decided and why.

### Routing Logic at Lug Creation

1. Load `_project_foundation.boundaries`
2. Classify: LOCAL (only this project) | FRAMEWORK (affects how projects work — including signal-type lugs, impact >= 8) | SPOKE/{id} (belongs to another spoke)
3. Announce: `"Creating {type} '{title}' → {routed_to}"`
4. Wait for user confirmation
5. Record decision in `scope_verified_by`

See `wai-lug-schema-reference.md` for routing JSON example and worked test case.

---

## Conditional Loading Fields

- `load_always: true` — Auto-load on session start
- `verify_on_closeout: true` — Test/verify before closeout
- `verification_count: N` — Times verified so far
- `verification_target: 5` — Target verifications (default 5)

---

## Signal vs Task vs Phone-Home

| Type | Purpose | AI Execution? |
|------|---------|--------------|
| `task` | Track work item | NO — add to tracker |
| `signal` | Patch-now alert (impact >= 8) — `routed_to: "FRAMEWORK"` | NO — write to `WAI-Spoke/signals/inbound/` |
| `phone-home` | Request status | AUTO by learn |
| `foundation` | Project identity | NO — defines project |

---

PEV completeness is required because a signal is a directive, not a note. Every spoke agent must be able to apply the patch without interpretation. A signal without PEV cannot be reliably actioned fleet-wide.

### Signal Scope Gate

Before emitting a signal lug, apply this test:

> **Does this learning apply to at least one other spoke besides the originator?**

- **Yes** → emit signal lug (`type: "signal"`, `routed_to: "FRAMEWORK"`) — framework resolves and distributes a teaching fleet-wide
- **No** → write a local lug or memory instead (local pattern = local record only)

Exception: if a shared framework tool needs a fix that affects all spokes using that tool, emit a framework impl lug (not a signal).

This gate was established after sessions where spoke-local patterns (UX choices, internal advisor ownership, single-spoke architecture decisions) were broadcast as signals with no value to other spokes.

---

## Anti-Patterns

**Never use ambiguous action verbs.** Lugs travel across sessions — explicit intent prevents misinterpretation:
- BAD: `{"action": "implement_feature"}` — executes now or tracks?
- GOOD: `{"request_type": "work_item_tracking", "do_not_execute_automatically": true}`

**Never use implicit context:**
- BAD: `{"task": "Update the config"}` — which config? how? why?
- GOOD: `{"task_type": "configuration_change", "target_file": "...", "change_description": "...", "tracking_only": true}`

See `wai-lug-schema-reference.md` for full anti-pattern examples.

---

## Related Skills

- `/wai-closeout` — Reconciles autosaves, creates session-summary
- `/wai (Step 3a: auto-discovery)` — Processes incoming lugs from incoming folder
- `/wai (Step 9b: auto-teach on closeout)` — Delivers outgoing lugs to target nodes

---

*Lugs = Persistent memory. CLARITY > BREVITY for persistent cross-session and cross-spoke communication.*

<!-- pipeline-verified-2026-03-25: skill-thrift-v1 applied -->
