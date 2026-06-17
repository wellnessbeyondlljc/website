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
    signal/{undelivered,delivered}/
    session-summary/               — all completed, no status subfolder
    other/{open,completed}/        — rare types (idea, policy, learning, etc.)
```

| What | Where | Notes |
|------|-------|-------|
| Active lugs | `lugs/bytype/*/open/` and `bytype/*/in_progress/` | Scanned at wakeup |
| Completed lugs | `lugs/bytype/{type}/completed/` | One file per lug |
| Signals (v2) | `WAI-Spoke/signals/{inbound,processed}/` + `signals/registry.json` | Separate from work lugs — applied at session start |
| Lug index | `WAI-Spoke/WAI-LugIndex.jsonl` | Lightweight lookup — on-demand only |
| Incoming/outgoing | `WAI-Spoke/lugs/incoming/` and `outgoing/` | Delivery channel only |
| Hub bulletin | `WAI-Hub/signals/incoming/` | High-impact lugs copied here at closeout |
| Reference docs | `WAI-Spoke/reference/` | Top-level, peer to lugs/sessions/skills |

**Storage rules:**
- **New lugs** → write to `lugs/bytype/{type}/open/{id}.json`
- **In-progress** → move to `lugs/bytype/{type}/in_progress/{id}.json`
- **Completed** → move to `lugs/bytype/{type}/completed/{id}.json`
- **Signals delivered** → move from `undelivered/` to `delivered/`
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
| `fw_ver` | `fw_ver` | **Framework version when lug was authored** (e.g. "3.0.0"). Set once at creation — never updated. Enables currency scoring. See `wai-lug-compat.md`. For teaching-derived fw_ver, see Series Versioning below. |
| `va` | `vibe_affinity` | **Work energy category** — one of: `build`, `fix`, `think`, `grind`, `ship`. Optional. Used by Ozi ROI scorer for tiebreaking when items have similar priority. |
| `impact` | `impact` | **Impact score** 1-10. Used by ROI scorer. Default inferred from type if absent. |
| `effort` | `effort` | **Effort score** 1-5. Used by ROI scorer. Default inferred from type if absent. |
| `urgency` | `urgency` | **Dispatch priority tier** 1-5 (default 3). 1=URGENT (immediate), 2=HIGH, 3=NORMAL, 4=LOW, 5=DEFER. Tiers sort before ROI — all tier-1 items dispatch before any tier-2. Backward compatible: omitted = tier 3. |
| `rt` | `routed_to` | Routing target: `LOCAL`, `FRAMEWORK`, `SIGNAL`, or `SPOKE/{spoke_id}` for cross-spoke |
| `spec_id` | `spec_id` | Optional. On implementation lugs: ID of the spec lug that defines the behavior being implemented. Singular — one primary spec per impl. |

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
| `signal` | Risk bulletin (impact >= 8) — patch or delivery flavor | No — store in `WAI-Spoke/signals/inbound/` (v2 schema, not bytype/) |
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
| `spec` | Living documentation of a spoke behavior — primary authoritative source for what a feature does, who it serves, and how it works | No — author at creation, update whenever behavior changes |

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
| `signal` | Patch-now alert broadcast to all spokes (impact >= 8) |
| `spec` | Living behavior specification — what a spoke feature does, who it serves, how it works |

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
| `model_fit` | `"haiku"` | **Model class for execution.** Implementation and coding lugs default to `"haiku"`. Set to `"sonnet"` for work requiring reasoning, architecture decisions, or multi-file changes. Set to `"opus"` for planning-heavy or high-stakes work. Tender reads this field to route lug passes. |

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
| `"SIGNAL"` | Patch-now alert broadcast to all spokes (impact >= 8) | hub bulletin + `WAI-Spoke/signals/inbound/` on each spoke; registry.json tracks applied |
| `"SPOKE/{spoke_id}"` | Cross-spoke routing | `{hub_path}/WAI-Hub/lugs/incoming/{spoke_id}/` + completed locally |
| `"ASSESSOR"` | Model performance telemetry | Deposited to `{hub_path}/WAI-Hub/advisors/assessor/inbox/` at closeout by `spoke-telemetry-closeout` |

**Default:** If not set, assume `LOCAL`. Ozi should confirm routing before creating.

### `scope_verified_by` (Required if routed_to != LOCAL)

`"user"` | `"ozi"` | `"framework"` | `"auto-signal"` — who decided and why.

### Routing Logic at Lug Creation

1. Load `_project_foundation.boundaries`
2. Classify: LOCAL (only this project) | FRAMEWORK (affects how projects work) | SIGNAL (impact >= 8, cross-spoke) | SPOKE/{id} (belongs to another spoke) | ASSESSOR (model telemetry capture)
3. Announce: `"Creating {type} '{title}' → {routed_to}"`
4. Wait for user confirmation
5. Record decision in `scope_verified_by`

See `wai-lug-schema-reference.md` for routing JSON example and worked test case.
See `wai-ozi-work-queue-monitor.md` → Routing Gate for dispatch-time enforcement of `routed_to`.

### Cross-Spoke Session Routing Decision Table

When you are working in spoke A and observe work that belongs elsewhere, use this table to decide where it goes:

| Situation | Correct Action | Wrong Action |
|-----------|---------------|-------------|
| You observe spoke B has a bug or improvement while working in spoke A | Write a lug to `{hub_path}/WAI-Hub/lugs/incoming/{spoke_b_id}/` (`routed_to: "SPOKE/{spoke_b_id}"`) | Emitting a framework signal |
| Work that ALL active spokes must apply immediately (impact >= 8) | Framework signal (`routed_to: "SIGNAL"`) | Writing to one spoke's inbox |
| Improvement to framework schemas, skills, or protocols | Framework impl lug to `framework/WAI-Spoke/lugs/incoming/` (`routed_to: "FRAMEWORK"`) | Writing to a specific spoke |
| Architectural decision owned by one spoke | Lug to that spoke's inbox (`routed_to: "SPOKE/{id}"`) | Broadcasting as a signal |
| Work only relevant to the spoke you are currently in | Local lug (`routed_to: "LOCAL"`) | Any of the above |

**Anti-pattern:** Do not use framework signals for spoke-specific Tender bugs, spoke-specific architecture decisions, or implementation details that only one spoke owns. Framework signals are broadcast-to-all — they waste every other spoke's session if the work isn't universal.

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
| `signal` | Patch-now alert (impact >= 8) | NO — store in `WAI-Spoke/signals/inbound/` (v2) |
| `phone-home` | Request status | AUTO by learn |
| `foundation` | Project identity | NO — defines project |

### Signal Required Fields

When creating a `signal` lug, include:

| Field | Required | Notes |
|-------|----------|-------|
| `routed_to` | **Yes** | Must be `"SIGNAL"` — marks this lug for hub bulletin delivery at closeout |
| `target` | **Yes** | Delivery destination: `"framework"`, `"hub"`, `"spokes"`, or `"spokes/{id}"` |
| `source_spoke` | **Yes** | `wheel.name` from this spoke's WAI-State.json — enables boomerang suppression |
| `perceive` | **Yes** | What to scan for on the target spoke — file path, config key, or behavior symptom |
| `execute` | **Yes** | Exact patch steps the receiving spoke must apply (array of numbered strings) |
| `verify` | **Yes** | How to confirm the patch was applied correctly |

A signal lug missing `routed_to` or `target` will not be delivered by closeout's primary trigger. The backlog sweep in step 9c will catch it but cannot route it correctly without `target`. Reject signal lug creation if either field is absent.

`source_spoke` enables boomerang suppression: when the hub routes a signal back to its originator, wakeup Step 5 checks this field (case-insensitive contains) against `wheel.name` and discards the duplicate instead of creating a redundant local lug.

PEV completeness is required because a signal is a directive, not a note. Every spoke agent must be able to apply the patch without interpretation. A signal without PEV cannot be reliably actioned fleet-wide.

### Teaching → Signal Loop-Close

When the framework generates a teaching that resolves a signal, add `signal_closes: {signal-id}` to the teaching frontmatter. `session-start.sh §0.6` (loop-close) reads this field at each spoke wakeup — when the matching teaching is found in `seed/ingest/processed/`, the registry entry is removed and the signal is archived to `signals/processed/`. This closes the v2 signal lifecycle automatically without human intervention.

### Signal Scope Gate

Before emitting a hub signal, apply this test:

> **Does this learning apply to at least one other spoke besides the originator?**

- **Yes** → emit hub signal (cross-spoke generalization)
- **No** → write a local lug or memory instead (local pattern = local record only)

Exception: if a shared framework tool needs a fix that affects all spokes using that tool, emit a hub task lug (not a signal).

This gate was established after sessions where spoke-local patterns (UX choices, internal advisor ownership, single-spoke architecture decisions) were broadcast as hub signals with no value to other spokes.

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
