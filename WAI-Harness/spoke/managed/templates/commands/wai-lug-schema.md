# WAI Lug Schema
> Fast path: load `wai-lug-schema-slim.md` first. Load this file only when deep protocol is needed.

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
| Signals (legacy) | `WAI-Spoke/signals/{inbound,processed}/` + `signals/registry.json` | **Deprecated** — old framework-patch mechanism. Do not create new signal lugs in spoke directories. |
| User signals | `{hub_path}/WAI-Hub/signals/incoming/` | User-action-required alerts. Written by spokes or Ozi. Read by all sessions at startup. NOT actionable by agents. |
| Lug index | `WAI-Spoke/WAI-LugIndex.jsonl` | Lightweight lookup — on-demand only |
| Incoming/outgoing | `WAI-Spoke/lugs/incoming/` and `outgoing/` | Delivery channel only |
| Hub bulletin | `WAI-Hub/signals/incoming/` | User-alert signals from spokes — read at every session start |
| Reference docs | `WAI-Spoke/reference/` | Top-level, peer to lugs/sessions/skills |

**Storage rules:**
- **New lugs** → write to `lugs/bytype/{type}/open/{id}.json`
- **In-progress** → move to `lugs/bytype/{type}/in_progress/{id}.json`
- **Completed** → move to `lugs/bytype/{type}/completed/{id}.json`
- **Index** → regenerated at closeout
- **Wakeup** → scans `bytype/*/open/` and `bytype/*/in_progress/` only

`WAI-Spoke/WAI-Signals.jsonl` and `WAI-Spoke/WAI-Lugs.jsonl` are **retired** (pre-v3.0 flat lug stores). Use `lugs/bytype/` for all lug operations. Do not create or write to the retired paths.

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
| `fw_ver` | `fw_ver` | **Framework version when lug was authored** (e.g. "3.0.0"). Set once at creation — never updated. Enables currency scoring. See `wai-lug-compat.md`. For teaching-derived fw_ver, see Series Versioning below. |
| `va` | `vibe_affinity` | **Work energy category** — one of: `build`, `fix`, `think`, `grind`, `ship`. Optional. Used by Ozi ROI scorer for tiebreaking when items have similar priority. |
| `impact` | `impact` | **Impact score** 1-10. Used by ROI scorer. Default inferred from type if absent. |
| `effort` | `effort` | **Effort score** 1-5. Used by ROI scorer. Default inferred from type if absent. |
| `urgency` | `urgency` | **Dispatch priority tier** 1-5 (default 3). 1=URGENT (immediate), 2=HIGH, 3=NORMAL, 4=LOW, 5=DEFER. Tiers sort before ROI — all tier-1 items dispatch before any tier-2. Backward compatible: omitted = tier 3. |
| `rt` | `routed_to` | Routing target: `LOCAL`, `FRAMEWORK`, or `SPOKE/{spoke_id}` for cross-spoke. Signal lugs do not use `routed_to` — write directly to `{hub_path}/WAI-Hub/signals/incoming/`. |
| `spec_id` | `spec_id` | Optional. On implementation lugs: ID of the spec lug that defines the behavior being implemented. Singular — one primary spec per impl. |
| `closes_epic_acs` | `closes_epic_acs` | Optional. List linking this lug to the **epic acceptance criteria it satisfies** — the mechanical edge `reconcile_epic_acs.py` uses to DERIVE epic AC status from evidence (never hand-maintained). Each entry is `{"ac": "AC8", "coverage": "full"\|"partial", "pending": "<what remains; REQUIRED iff coverage=partial>"}`. A bare string (`"AC8"`) is sugar for `{ac, coverage:"full"}`. **`coverage:full` is honored only if a `verification_test` whose `covers_ac` names THIS AC is green (`result:1`) and not stale** — a completed lug + green test that is built-not-wired / delivered-not-applied / loop-not-live is `coverage:partial` and reconciles to `[~]`, never `[x]`. |
| `suggested_skill` | `suggested_skill` | Optional. The exact skill command that resolves this lug (e.g. `/wai-foundation` for a `missing_foundation` remediation lug). When set, the wakeup work-queue surfaces it as the **first** recommended action — a one-line, copy-paste CTA, not a paragraph of file edits. |
| `hyp` | `hypothesis` | Optional (ideation). **Why** we're doing this — the belief that motivates the work. Capture at creation when ideating with an agent so intent is shared, not implied. |
| `lift` | `expected_lift` | Optional (ideation). The **measurable improvement expected** (e.g. "closeout cost −40%", "−4 tool calls/wakeup"). Stated as a target before the work runs. |
| `measure` | `measure` | Optional (ideation). **How** we'll check the lift after implementing (the metric + where it's read). At closeout/review, compare actual vs `expected_lift`. |

> **Ideation capture (hypothesis/expected_lift/measure):** when creating `idea`/`feature` lugs during ideation, fill these three so agent and user are aligned on *why* and can measure whether the lift landed. This is the lightweight, lug-resident form of hypothesis-grounded work — no external Realizer service required.

**Title Policy:**
- **No generic session summaries:** "Session 35 summary" is BANNED.
- **Good:** "Session 35: Successfully implemented chat-to-track epic and historian dual-watermark"
- **Bad:** "Task: Update state"

Both short and full key forms are valid. Prefer short keys for storage efficiency.

---

## Series Versioning (Teaching-Derived fw_ver)

Spokes accumulate teachings as a version string. Each absorbed teaching contributes a 3-char fingerprint and a complexity weight.

### Spoke version string format

```
{series}.{YYYYMMDD}-{fp1}.{fp2}.{fp3}...
```

- `series` — integer, starts at 1, increments when accumulated weight reaches 100 or hub emits a series-close teaching
- `YYYYMMDD` — date of last absorbed teaching (human sortability only, not included in MD5)
- `fpN` — fingerprints in chronological adoption order (append-only)

**Example:** `3.20260402-a7f.3bc.k9m.p2r`

### fw_ver derivation for lug use

```
fw_ver = MD5("{series}.{alpha-sorted fingerprints}")
```

Alpha-sorted ensures two spokes with identical absorbed teachings produce identical `fw_ver` regardless of adoption order.

**Example input:** `3.3bc.a7f.k9m.p2r` → MD5 hash → `fw_ver` value

### Series boundary rules

- **Automatic close:** accumulated weight reaches 100 points
- **Early close:** hub emits a `series-close` teaching — spoke bumps series on absorption
- **On close:** series increments, fingerprint list clears, MD5 space resets
- **At series close, fingerprint count reflects series character:** 4 fingerprints = generational shift, 97 = stabilization period

### Teaching weight scale

| Weight | Meaning |
|--------|---------|
| 1 | Patch / minor fix / wording update |
| 5 | Behaviour update / protocol tweak |
| 10 | Schema or protocol change |
| 25 | Architectural addition or new advisor |

### Fingerprint generation

`fingerprint = first 3 chars of MD5("{teaching-id}:{weight}")`

Weighting the hash input ensures changing a teaching's weight invalidates its fingerprint (integrity property).

### Under the base+patches model (v3+)

The "series" anchor is now `_harness.base_version` and the fingerprinted units are the **patches** in `base/teachings/index.json` (each patch carries `fingerprint` + `weight`). Derivation:

```
_harness.fw_ver = MD5("{base_version}.{alpha-sorted adopted-patch fingerprints}")[:12]
```

Two spokes on the same base that adopted the same patches derive an identical `fw_ver` regardless of order — making fleet state auditable. Cutting a new base resets the patch set (and thus the fingerprint space), exactly the "series close" behaviour above. `06-verify.md` computes `fw_ver` into the ledger during adoption.

---

## Status Values

| Code | Meaning |
|------|---------|
| `o` or `open` | Open / pending — not started |
| `p` or `in-progress` | In progress — actively being worked |
| `c` or `closed` or `resolved` | Complete / closed |
| `b` or `blocked` | Blocked by another lug or external dependency |

### Spec Lug Lifecycle

Spec lugs use a distinct 3-state lifecycle — they do NOT use the standard open/completed cycle because spec lugs do not "complete". They stay live as long as the feature exists.

| State | Meaning |
|-------|---------|
| `draft` | Being authored — not yet stable enough to reference |
| `active` | Authoritative — impl lugs reference this; SpecIndex includes it |
| `deprecated` | Behavior retired or replaced by another spec — kept for history |

Spec lugs are stored at `WAI-Spoke/lugs/bytype/spec/{draft,active,deprecated}/{id}.json`.

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
| `signal` | User-action-required alert — a message from a spoke or Ozi to the human user requiring their direct decision or action. NOT a framework patch. NOT actionable by agents alone. | No — write to `{hub_path}/WAI-Hub/signals/incoming/{id}.json`; displayed at session start |
| `foundation` | Project identity, boundaries, approach | No — defines the project |
| `session-summary` | Completed session record (autosaves reconciled) | No — archive only |
| `autosave` | Crash-recovery checkpoint from mid-session | Reconcile at closeout |
| `policy` | Project rules or constraints | No — reference document |
| `observation` | Factual observation logged for pattern detection | No — record |
| `learning` | Cross-session insight worth preserving | No — record |
| `hypothesis` | Proposed advisor behavior change generated by EvolutionEngine when recurrence threshold is met. Routes to lead advisor for review. Created at `bytype/other/open/hyp-{advisor}-{pattern}-{ts}.json`. | No — review required |
| `maintenance` | Infrastructure or tooling work | No — add to tracker |
| `core-protocol` | Framework protocol documentation | No — reference document |
| `delivery_confirmation` | Confirms lug was delivered to target spoke | Auto-acknowledged |
| `phone-home` | Hub requests status report from spoke | Auto-handled by learn |
| `config` | Configuration update for node | Applied during learn |
| `session` | Historical session record (legacy) | No — archive only |
| `challenge` | Problem-centric anchor for idea lugs | No — append-only in WAI-Challenges.jsonl |
| `spec` | Living documentation of a spoke behavior — primary authoritative source for what a feature does, who it serves, and how it works | No — author at creation, update whenever behavior changes |
| `chain` | Portable, resumable work-coordination unit — groups child lugs into a claimable execution sequence with TTL-based claiming, session scoping, and deferred-child overflow. Sits between an epic (strategic) and implementation lugs (atomic). Stored at `bytype/chain/{status}/{id}.json`. | No — claimed at session startup via claim registry |

---

## Chain Lug

A `chain` lug coordinates multi-session work with distributed claiming. Unlike epics (strategic) or implementation lugs (atomic), chains are the execution unit — each session claims one, plans what fits in budget, executes, and defers overflow.

**Status values:** `open | claimed | in_progress | deferred | completed`

**Required fields (in addition to standard id/type/status/created_at):**
- `goal`: string — the Work Goal this chain accomplishes (one sentence, cross-session)
- `execution_mode`: `sequential | parallel`
- `children`: array of child lug IDs (ordered for sequential, unordered for parallel)
- `completed_children`: array of child lug IDs completed in prior sessions
- `claimed_by`: session_id or null
- `claimed_at`: ISO-8601 or null
- `ttl_hours`: int default 6 — claim expires at claimed_at + ttl_hours
- `session_plan`: object — populated when claimed:
  - `model`: model_id this session will use
  - `budget_tokens`: token ceiling for this claim
  - `planned_children`: child lug IDs this session will attempt
  - `deferred_children`: child lug IDs deferred to next session
  - `file_scope`: files this session will touch (conflict lock)

**Claim registry:** Supabase `wai_claims` table (primary) or `WAI-Spoke/runtime/claims-local.json` (fallback for single-Ozi spokes without Supabase). PRIMARY KEY on `chain_id` makes claiming atomic — PK collision rejects a second concurrent claim.

**Storage:** `WAI-Spoke/lugs/bytype/chain/{open,in_progress,completed}/{id}.json`

## Contract Fields (Lease + Verify + Provenance)

Every lug is a hole in a [pattern](wai-pattern.md) — the contract. These fields make any lug leasable (so parallel streams don't collide) and verifiable (so a pattern can certify it). The lease **generalizes the chain-claim mechanism above to lug granularity**; reuse the same `wai_claims` atomicity, do not reinvent it.

**Lease fields:**
- `held_by`: session_id holding the lease, or null
- `held_at`: ISO-8601 claim time, or null
- `lease_ttl_hours`: int, default `4` — lease expires at `held_at + lease_ttl_hours`

**Lease rules:**
- **Atomic claim** via `wai_claims` PK (key = `lug_id`) with `claims-local.json` fallback — a second concurrent claim is rejected by PK collision.
- **Readers skip held lugs** — Ozi/dispatch/sub-agents route around any lug held by a *live* session (verify-before-action gate).
- **Expiry auto-releases** at wakeup/dispatch when `held_at + lease_ttl_hours` has passed with no live holder.
- **Bias to done over holding:** if a worker can't finish within the TTL, it emits a *partial* bolt for what it certified and releases the lease — the next worker resumes from proof, not archaeology.

**Verification field:**
- `verify_mode`: `mechanical | attested | human` — how this lug's `verify[]` criteria are certified when its pattern closes. `mechanical` runs `verify[]` as a runnable assertion; `attested` requires a named verifier (e.g. the `lug-reviewer` agent) to sign; `human` requires Mario to sign. Nothing certifies uncertified.

**Provenance field:**
- `provenance`: `{ source_lugs: [], source_teachings: [] }` — the inputs that led to this lug. Feeds the pattern's `provenance` (the versioned DNA) so any delivered work is traceable to what manifested it.

See `spec-goal-chain-v1` for full schema, constraints, TTL expiry behavior, and claim/release protocol.

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

## Spec Lug

Spec lugs are the **primary authoritative source** for understanding what this spoke does. An agent loading the SpecIndex and relevant spec lugs should fully understand spoke behavior without reading code.

**Scope:** Spec lugs document THIS SPOKE's behaviors — features, workflows, protocols as experienced by admins, users, prospects, and agents. Not general WAI framework internals.

**Audience values:** `admin` | `user` | `prospect` | `agent` | `dev`

**subject.kind values:** `feature` | `workflow` | `protocol` | `integration` | `advisor` | `schema`

**Required fields** (beyond standard id/type/status/created_at/gb/fw_ver/impact):
- `subject`: `{kind, id, label}` — what feature/workflow/protocol this documents
- `version`: SemVer string — bump on meaningful content change
- `updated_at`: ISO-8601 — updated on every content change
- `what`: 2-3 sentence plain-language description of what this feature does
- `why`: Why it exists — what breaks or is missing without it
- `audience`: Array of audience values
- `use_cases`: Array of `{title, trigger, outcome, persona}` — at least 1
- `patterns`: Array of `{name, description}` — 0 or more notable usage patterns
- `how`: `{trigger, steps_summary[], constraints[]}` — how the feature works
- `when`: `{triggers[], not_when[], frequency}` — when it runs or is used
- `schema`: `{inputs[], outputs[], state_changes[]}` — data flow
- `constraints`: Array of hard rules the behavior must follow
- `tests`: Array of `{test_file, test_names[], coverage_area, last_verified}` — empty list OK
- `impl_lugs`: Array of impl lug IDs that build/change this behavior
- `health`: `{test_coverage, last_impl_lug_completed, spec_drift_risk, open_questions[]}`

**Spec content lives in JSON only** — never in markdown files. The spec IS the documentation.

**Discovery:** `WAI-SpecIndex.jsonl` — one line per spec. Query: `grep '"subject_id": "ozi-queue"' WAI-SpecIndex.jsonl` returns the entry with `folder` path. Load `{folder}/{id}.json` for full spec. Two operations, no context explosion. (Note: index uses standard JSON spacing — `"subject_id": "value"` not `"subject_id":"value"`)

**Evergreen rule:** When an implementation lug with `spec_id` moves to completed, the delivering agent must either (a) confirm the spec still matches the behavior, or (b) create a follow-up draft spec update lug. Spec drift is invisible until the next agent reads stale documentation.

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
| `signal` | User-action-required alert — message from spoke/Ozi to the human user. NOT a framework patch. Stored at hub (`signals/incoming/`), shown at session start. |
| `spec` | Living behavior specification — what a spoke feature does, who it serves, how it works |
| `chain` | Claimable multi-session coordination unit — groups child lugs into a session-scoped execution sequence with TTL claiming and deferred-child overflow |

### work.kind Field

When creating a `work` lug, set `work.kind` to classify the work:

| work.kind | Replaces | Use when |
|-----------|---------|---------|
| `task` | type: "task" | Defined unit of work |
| `bug` | type: "bug" | Defect or broken behavior |
| `feature` | type: "feature" | New capability |
| `implementation` | type: "implementation" | Capability rollout |

**Dual-Read Compatibility:** Existing lugs with `type: "task"`, `type: "bug"`, or `type: "feature"` remain valid. Do not bulk-rewrite. New lugs should use canonical types. Treat `type: "task"` as equivalent to `type: "work", work.kind: "task"`.

**Bug subtype — Scout Finding:** A bug lug produced by an automated scout job. Add these optional fields alongside standard bug fields: `scout_job_id` (stable scout id), `verification_result` `{score, passed, verification_type, details}`, `self_finding_subtype` (`confusion | refusal | null`), `repeat_fire_count` (starts 1, increment on re-fire — do not create new lugs), `run_log_ref` (activity_events row id). Full schema: `WAI-Lug-Schema-Spec.md § Bug Type: Scout Finding Subtype`.

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
| `files_to_create` | `[]` | Paths agent must create. Relative to project root. Sub-agent dispatch only. |
| `files_to_edit` | `[]` | Paths agent must modify. Sub-agent dispatch only. |
| `files_to_read` | `[]` | Paths agent reads for style/schema/context (not modified). Sub-agent dispatch only. |
| `wave` | `null` | Wave identifier (`"A"`, `"B"`, `"C"`, …) for parallel dispatch ordering. Wave A = zero dependencies; Wave B = blocked only by Wave A; etc. |
| `dependencies` | `[]` | Lug IDs this lug waits on (must complete before this one starts). |
| `blocking` | `[]` | Lug IDs waiting on this one (informational — populated by planner, not author). |
| `tags` | `[]` | Empty array |
| `phase` | `null` | Phase membership ID (e.g. `"p1-foundation"`) — groups items for milestone tracking. Cross-reference `project_ozi_directive_crew_design.md` for crew phases. |
| `phase_order` | `null` | Numeric ordering within a phase (lower = earlier) |
| `execute_when` | `null` | Conditional trigger — see Execute-When Gates section below |
| `model_fit` | `"haiku"` | **Model class for execution.** Implementation and coding lugs default to `"haiku"`. Set to `"sonnet"` for work requiring reasoning, architecture decisions, or multi-file changes. Set to `"opus"` for planning-heavy or high-stakes work. Tender reads this field to route lug passes. |
| `state` | `null` | Fine-grained sub-status within `s`, free-form string |
| `risk_tier` | `'standard'` | One of: `low`, `standard`, `elevated`, `critical` |
| `lead_advisor` | `null` | Crew folder slug, e.g. `delivery-manager` |
| `consulting_advisors` | `[]` | Array of crew folder slugs |
| `execution_mode` | `'manual'` | One of: `manual`, `subagent`, `tender`, `gastown` |
| `model_override` | `null` | Model id that wins over model_fit when present |
| `outcome` | `null` | One of: shipped, shipped_with_rework, abandoned, superseded. Set at completion. Null on open lugs. |
| `gitnexus_symbols` | `[]` | Array of refactor-stable GitNexus symbol IDs touched by this lug. Populated post-implementation. |
| `execution_substrate` | `null` | Execution substrate for automated dispatch. Set to `"gastown"` when lug qualifies for gastown batch dispatch. Evaluated at CREATE time. |
| `gt_convoy_hint` | `null` | Optional. Brief one-sentence description for the gastown Mayor convoy context. Set alongside `execution_substrate: "gastown"`. |

> **Sub-agent dispatch fields:** `files_to_create`, `files_to_edit`, `files_to_read`, `wave`, `dependencies`, and `blocking` are optional. Populate them only for lugs intended for sub-agent dispatch. Omitting them on human-executed lugs is correct.

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

1. **CREATE** — Write to `lugs/bytype/{type}/open/{id}.json` with `s: "o"`. Ensure PEV fields are present. After setting all required fields, inject `recommended_model` from Navigator context profiles:

```python
import json, os, datetime

nav_rec_path = "WAI-Spoke/advisors/navigator/recommendations-current.json"

PROFILE_MAP = {
    "implementation": lambda effort: "coding_high" if effort >= 3 else "coding_low",
    "bug":            lambda effort: "debugging_medium",
    "feature":        lambda effort: "planning_high" if effort >= 3 else "coding_low",
    "epic":           lambda effort: "planning_high",
    "task":           lambda effort: "coding_low",
    "review":         lambda effort: "review_low",
}

if os.path.exists(nav_rec_path):
    recs = json.load(open(nav_rec_path))
    valid_through = recs.get("valid_through")
    is_fresh = valid_through and datetime.datetime.fromisoformat(valid_through) > datetime.datetime.now(datetime.timezone.utc)
    effort = lug.get("effort", 3)
    lug_type = lug.get("type", "task")
    profile_id = PROFILE_MAP.get(lug_type, lambda e: "coding_low")(effort)
    profile = recs.get("profiles", {}).get(profile_id, {})
    slot = profile.get("default") or {}
    if slot.get("model_id"):
        lug["recommended_model"] = {
            "model_id": slot["model_id"],
            "provider": slot["provider"],
            "score": slot.get("score"),
            "profile_id": profile_id,
            "rationale": f"Navigator {profile_id} default slot (score {slot.get('score')})",
            "warnings": slot.get("warnings", []),
            "stale": not is_fresh,
        }
        # Anthropic fallback — always reachable in Claude Code; surface when default is a different provider
        if slot.get("provider") != "anthropic":
            RANKED_SLOTS = ("high_confidence", "default", "cost_optimized", "fast", "fallback")
            anthropic_candidates = [
                (sn, profile.get(sn, {}))
                for sn in RANKED_SLOTS
                if profile.get(sn, {}).get("provider") == "anthropic"
                   and profile.get(sn, {}).get("model_id")
            ]
            if anthropic_candidates:
                best_name, best = max(anthropic_candidates, key=lambda x: x[1].get("score") or 0)
                lug["recommended_model"]["anthropic_fallback"] = {
                    "model_id": best["model_id"],
                    "score": best.get("score"),
                    "slot": best_name,
                    "note": "Always accessible in Claude Code — use when external provider API not configured",
                }
    else:
        lug["recommended_model"] = {
            "model_id": None, "provider": None, "profile_id": profile_id,
            "score": None, "rationale": None, "warnings": ["catalog_empty_or_stale"], "stale": not is_fresh
        }
# If recommendations absent, omit the field (Navigator not yet operational on this spoke)
```

#### GT Candidacy Check

After Navigator injection, evaluate gastown eligibility and stamp `execution_substrate` if applicable:

```python
import os

# GT candidacy: eligible when all conditions met
gt_eligible = (
    lug.get("model_fit") == "haiku"
    and lug.get("type") in ("work", "task", "feature", "implementation", "impl")
    and not (lug.get("execute_when") or {}).get("manual_gate")
    and os.path.isdir(os.path.expanduser("~/projects/gastown"))
)

if gt_eligible:
    lug["execution_substrate"] = "gastown"
    # Derive a one-sentence convoy hint from the lug title/one_liner
    hint_source = lug.get("one_liner") or lug.get("title") or lug.get("t", "")
    lug["gt_convoy_hint"] = hint_source[:120].rstrip()
    print(f"GT candidacy: ELIGIBLE — execution_substrate set to 'gastown'")
else:
    reasons = []
    if lug.get("model_fit") != "haiku": reasons.append(f"model_fit={lug.get('model_fit')} (need haiku)")
    if lug.get("type") not in ("work", "task", "feature", "implementation", "impl"): reasons.append(f"type={lug.get('type')}")
    if (lug.get("execute_when") or {}).get("manual_gate"): reasons.append("manual_gate=true")
    if not os.path.isdir(os.path.expanduser("~/projects/gastown")): reasons.append("gastown not installed")
    print(f"GT candidacy: NOT ELIGIBLE — {'; '.join(reasons) or 'unknown'}")
```

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
| `"SIGNAL"` | **Deprecated** — do not use. Signal lugs are user alerts; write directly to `{hub_path}/WAI-Hub/signals/incoming/` with no `routed_to` needed. | ignored |
| `"SPOKE/{spoke_id}"` | Cross-spoke routing | `{hub_path}/WAI-Hub/lugs/incoming/{spoke_id}/` + completed locally |
| `"ASSESSOR"` | Model performance telemetry | Deposited to `{hub_path}/WAI-Hub/advisors/assessor/inbox/` at closeout by `spoke-telemetry-closeout` |

**Default:** If not set, assume `LOCAL`. Ozi should confirm routing before creating.

#### Delivery

Cross-spoke lugs are **compose-and-send**: deliver immediately after creation. Do not queue and wait for closeout.

**Pre-delivery checklist** (run before every delivery):
- `perceive` non-empty
- `execute` non-empty
- `verify` non-empty
- `destination_wheel_id` set and resolvable in hub-registry.json
- `acceptance_criteria` is a non-empty list
- `effort_score` is a number or T-shirt size — both formats are valid fleet-wide. Numeric: 1–9. T-shirt: `XS`=1, `S`=2, `M`=3, `L`=5, `XL`=8, `XXL`=13. Tools that read `effort_score` must coerce via `_coerce_number()` — never call `float()` directly on this field.
- `model_fit` is one of: `haiku`, `sonnet`, `opus`
- For `impl`/`feature`/`task`: `target_files` or `files_to_edit` present

If any check fails: fix the lug. Do not deliver a draft.

**Delivery action** (after checklist passes):
1. Write lug to `WAI-Spoke/lugs/outgoing/{id}.json` (local audit record)
2. Read hub-registry.json → resolve `destination_wheel_id` to spoke path
3. `\cp WAI-Spoke/lugs/outgoing/{id}.json {target_path}/WAI-Spoke/lugs/incoming/{id}.json`
4. Set `delivered_at: {iso_timestamp}` and `status: delivered` in the outgoing copy

**Closeout Step 9 is a sweep backstop**, not the primary delivery path. Lugs that reach closeout undelivered are considered delivery failures — they were created but not sent.

### `scope_verified_by` (Required if routed_to != LOCAL)

`"user"` | `"ozi"` | `"framework"` | `"auto-signal"` — who decided and why.

### Routing Logic at Lug Creation

1. Load `_project_foundation.boundaries`
2. Classify: LOCAL (only this project) | FRAMEWORK (affects how projects work — impl/task lugs that improve framework schemas, skills, or protocols) | SPOKE/{id} (belongs to another spoke) | ASSESSOR (model telemetry capture)
3. Announce: `"Creating {type} '{title}' → {routed_to}"`
4. Wait for user confirmation
5. Record decision in `scope_verified_by`

See `wai-lug-schema-reference.md` for routing JSON example and worked test case.
See `wai-ozi-work-queue-monitor.md` → Routing Gate for dispatch-time enforcement of `routed_to`.

### Cross-Spoke Session Routing Decision Table

When you are working in spoke A and observe work that belongs elsewhere, use this table to decide where it goes:

| Situation | Correct Action | Wrong Action |
|-----------|---------------|-------------|
| You observe spoke B has a bug or improvement while working in spoke A | Write a lug to `{hub_path}/WAI-Hub/lugs/incoming/{spoke_b_id}/` (`routed_to: "SPOKE/{spoke_b_id}"`) | Routing to hub incoming (hub never relays to spokes) |
| Improvement to framework schemas, skills, or protocols | Framework impl/task lug to `framework/WAI-Spoke/lugs/incoming/` (`routed_to: "FRAMEWORK"`) | Writing a signal lug |
| Something the USER must decide or act on (not agent-resolvable) | Signal lug (`type: "signal"`) → write to `{hub_path}/WAI-Hub/signals/incoming/` | Creating an impl/task lug (user won't see it at startup) |
| Architectural decision owned by one spoke | Lug to that spoke's inbox (`routed_to: "SPOKE/{id}"`) | Any broadcast mechanism |
| Work only relevant to the spoke you are currently in | Local lug (`routed_to: "LOCAL"`) | Any of the above |

**Anti-pattern:** Do not create signal lugs for framework fixes. A gap you want the framework to address is a `task` or `implementation` lug with `routed_to: "FRAMEWORK"`. Signal lugs are for the user — things no agent can resolve without human input. `routed_to: "SIGNAL"` is deprecated; do not use.

---

## Conditional Loading Fields

- `load_always: true` — Auto-load on session start
- `verify_on_closeout: true` — Test/verify before closeout
- `verification_count: N` — Times verified so far
- `verification_target: 5` — Target verifications (default 5)

---

## Signal vs Task vs Framework Fix

| Type | Audience | Who acts? | Where stored? |
|------|---------|-----------|--------------|
| `signal` | **Human user** — something only you can decide or action | User only — agents show it, do not resolve it | `{hub_path}/WAI-Hub/signals/incoming/` |
| `task` / `implementation` | Agent or user | Agent executes at next session | `lugs/bytype/{type}/open/` |
| Framework fix (`routed_to: "FRAMEWORK"`) | Framework team / Ozi | Framework agent implements, publishes teaching | `lugs/bytype/{type}/open/` with `routed_to: "FRAMEWORK"` |
| `phone-home` | Hub requesting status | AUTO by learn | Handled by spoke learn protocol |

**Decision rule:** If a human must read it and choose what to do → signal. If an agent can implement it without human input → task/impl lug. If it improves the framework for all spokes → task/impl with `routed_to: "FRAMEWORK"`.

### Signal Required Fields

When creating a `signal` lug, include:

| Field | Required | Notes |
|-------|----------|-------|
| `title` | **Yes** | Short, imperative — "Review Ozi dispatch queue: 3 lugs stalled >72h" |
| `body` | **Yes** | What the user needs to know. Include context, not just symptoms. |
| `source_spoke` | **Yes** | `wheel.name` from this spoke's WAI-State.json |
| `created_at` | **Yes** | ISO-8601 timestamp |
| `status` | **Yes** | `"open"` — set to `"acknowledged"` when user reads and responds |
| `requires_decision` | No | Array of decision options if user must choose a path |

Signals do **not** require `routed_to`, `perceive`, `execute`, or `verify` — those fields are for agent-executable lugs. A signal is a message, not a directive.

### Signal Lifecycle

```
created at spoke → written to hub/WAI-Hub/signals/incoming/ → shown at session start →
user reads and acts → user or agent marks status: "acknowledged" → archived to hub/WAI-Hub/signals/processed/
```

Signals must not accumulate. Each session start shows open signals. If a signal has no response after 7 days, Ozi may escalate with a reminder in the session brief.

### When NOT to Use a Signal

- The agent can resolve it without you → use `task` lug
- It's a framework improvement → use `task`/`implementation` with `routed_to: "FRAMEWORK"`
- It's informational and requires no action → write a `learning` lug or memory file
- It's fleet-wide behavior → framework publishes a teaching after implementing it

The old "fleet-wide patch via signal" mechanism is retired. Emit a framework impl lug instead — the framework implements and publishes a teaching; spokes absorb it at wakeup.

### Migration Note (v2 → v3 Signal Semantics)

Existing signal lugs in `WAI-Spoke/lugs/bytype/signal/` are **legacy**. Do not create new ones there.

| Old pattern | New pattern |
|------------|------------|
| `type: "signal"`, `routed_to: "FRAMEWORK"` (fleet patch) | `type: "task"` or `"implementation"`, `routed_to: "FRAMEWORK"` |
| `WAI-Spoke/signals/inbound/` patch files | Deprecated — do not create new patch files there |
| `WAI-Hub/signals/incoming/framework/` | Deprecated path — no new files |
| New user alert to human | `type: "signal"` → write to `{hub_path}/WAI-Hub/signals/incoming/{id}.json` |

The spoke-local `signals/` directory (`inbound/`, `processed/`, `registry.json`) is legacy infrastructure. Do not write new signal lugs there. The directory is preserved only for reading existing archived signals.

---

## Advisor Attribution

When a lug is created by an advisor (not directly by the user or Ozi), it must carry attribution fields so contribution and ROI can be measured.

### Attribution fields (add to any advisor-generated lug)

| Field | Type | Description |
|-------|------|-------------|
| `created_by_advisor` | string | Advisor ID that produced this lug (e.g. `"historian"`) |
| `created_by_department` | string \| null | Department ID, if advisor belongs to one |
| `advisor_run_id` | string | Run ID from the advisor's `runs.jsonl` entry |
| `advisor_confidence` | float 0-1 | Advisor's self-reported confidence in this item |
| `advisor_origin_type` | string | `specialist` \| `manager` \| `synthesis` |

### Advisor Run record schema

Appended to `WAI-Spoke/advisors/{advisor_id}/runs.jsonl` after each advisor execution.

```json
{
  "run_id": "run-{advisor_id}-{YYYYMMDD-HHMM}",
  "advisor_id": "historian",
  "department_id": null,
  "started_at": "2026-04-02T00:00:00Z",
  "completed_at": "2026-04-02T00:05:00Z",
  "trigger_type": "schedule",
  "trigger_reason": "weekly cadence elapsed",
  "inputs_used": ["context/snapshot-2026-04-01.md"],
  "findings_count": 3,
  "work_items_proposed": 2,
  "work_items_accepted": 1,
  "questions_for_ozi": [],
  "next_schedule_recommendation": "weekly",
  "updated_relevance_conditions": {},
  "confidence": 0.85,
  "model_class": "sonnet"
}
```

### Lifecycle event schema

Appended to `WAI-Spoke/advisors/lifecycle.jsonl` on structural advisor changes.

```json
{
  "event_id": "evt-{advisor_id}-{ts}",
  "advisor_id": "archie",
  "event_type": "run_completed",
  "ts": "2026-04-02T00:05:00Z",
  "reason": "weekly schedule",
  "changed_fields": [],
  "authorized_by": "ozi"
}
```

**Event types:** `created`, `instantiated_from_template`, `charter_updated`, `focus_updated`, `schedule_updated`, `run_completed`, `moved_department`, `paused`, `retired`, `reactivated`

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

## Crew Fields

This section documents additional fields relevant to the Crew architecture, detailing their purpose, allowed values, and typical ownership. These fields are additive and optional for backward compatibility.

- **`state`** (string, default: `null`): A fine-grained sub-status providing more context than the top-level `status` field. Free-form string.
  - *Set/Read by:* Delivery Manager (Dana), Product Strategist (Pete), all sub-agents.

- **`risk_tier`** (string, default: `'standard'`): Categorizes the risk associated with the lug.
  - *Allowed values:* `low`, `standard`, `elevated`, `critical`.
  - *Set/Read by:* Product Strategist (Pete), Architect (Archie).

- **`lead_advisor`** (string, default: `null`): The designated crew advisor (by folder slug) primarily responsible for this lug.
  - *Example:* `delivery-manager`, `product-strategist`, `architect`.
  - *Set/Read by:* Delivery Manager (Dana).

- **`consulting_advisors`** (array of strings, default: `[]`): A list of additional crew advisors (by folder slug) who should be consulted or informed about this lug.
  - *Example:* `['ux-designer', 'security-reviewer']`.
  - *Set/Read by:* Delivery Manager (Dana), Product Strategist (Pete), Architect (Archie).

- **`execution_mode`** (string, default: `'manual'`): Specifies how the execution of this lug is intended to be carried out.
  - *Allowed values:* `manual`, `subagent`, `tender`, `gastown`.
  - *Set/Read by:* Delivery Manager (Dana), Architect (Archie), Tender.

- **`model_override`** (string, default: `null`): An optional field to specify a particular model ID (e.g., `claude-opus-4-7`, `gemini-1.5-pro`) that should be used for executing this lug, overriding `model_fit`.
  - *Set/Read by:* Delivery Manager (Dana), Architect (Archie).

## Schema Changelog

2026-05-20: +state, +risk_tier, +lead_advisor, +consulting_advisors, +execution_mode, +model_override (Phase A crew architecture, all additive)
