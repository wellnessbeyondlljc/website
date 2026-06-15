# WAI Improve

**Improvement Idea Protocol — capture, evaluate, and prioritize system improvement ideas in the context of this spoke.**

---

## Execution Context

- **Nodes:** spoke, hub
- **Exposure:** spoke.chat:local
- **Trigger:** User submits an idea, agent surfaces a pattern, or `/wai-improve` is called directly

## When to Use

- User has an improvement idea (new or from backlog)
- Agent detects friction, inefficiency, or a recurring pattern worth addressing
- Backlog review — sorting and reframing stale ideas
- After a session reveals a systemic gap worth capturing

---

## Core Principle

**Separate the challenge from the hypothesis.**

The challenge is the *problem worth solving*. The hypothesis is *one possible solution*.
Old ideas almost always have a still-valid challenge — only the hypothesis goes stale. Never discard the challenge when the hypothesis is outdated. Reframe.

**You cannot evaluate an idea without understanding the project.** Load context and scan the system before evaluating anything.

---

## Execution Flow

```
Step 0: Load spoke context (foundation, boundaries, phase)
   ↓
Step 1: Intake (challenge, hypothesis, origin, scope)
   ↓
Step 2: Similarity and fit check ← must complete before refinement or scoring
   ↓
Step 3: Refinement questions (informed by Steps 0 + 2)
   ↓
Step 3b: Challenge matching (link refined statement → WAI-Challenges.jsonl)
   ↓
Step 4: Evaluation and scoring
   ↓
Step 5: Output as idea lug (or merge/supersede/discard decision)
```

Steps 2 and 3 are the fitting work. They happen in conversation, before any lug is created. A lug that skips these steps is not fully processed and should not be promoted.

---

## Step 0: Load Spoke Context (Required)

### 0a. Read Foundation

From `WAI-Spoke/WAI-State.json`, extract: `_project_foundation.identity.one_liner`, `success_looks_like`, `boundaries.in_scope`, `boundaries.out_of_scope`, `boundaries.constraints`, `philosophy.core_principle`, `approach.stack_or_tools`, `context.current_phase`.

Also check `WAI-Spoke/lugs/bytype/other/open/` for any `ty: "foundation"` lug — may be richer than WAI-State.json.

### 0b. Foundation Completeness Check

| Signal | What It Means |
|--------|--------------|
| `identity.one_liner` is null or generic | Cannot evaluate fit or velocity — ask user |
| `boundaries.in_scope` is empty | Cannot evaluate system fit |
| `boundaries.constraints` is empty | Cannot evaluate cost or risk |
| `context.current_phase` is null | Cannot weight urgency |
| No foundation lug exists at all | **Stop. Run `/wai-foundation` first.** |

If critical fields are missing, ask rather than inventing context.

### 0c. Build Scoring Context

Before evaluating any idea, write a one-line definition of each scoring dimension in spoke-specific terms:
- **Velocity lift:** what does "faster" mean here?
- **System fit:** what is aligned vs out of scope?
- **Implementation cost:** what makes something cheap or expensive here?
- **Generality:** who does this affect?

Show these to the user at the start of a backlog session so the rubric is shared.

---

## Step 1: Intake

Extract or prompt for four things:

**Challenge** — the stable part. What breaks, slows, or is missing?
- If vague: "What breaks or feels wrong without this?" Must be present before proceeding.

**Hypothesis** — the testable part. Format: "If we [do X], then [outcome Y] because [reason Z]"

**Origin** — `user` / `agent` / `signal` / `backlog`

**Scope** — `skill` / `protocol` / `schema` / `tooling` / `multi` / `trivial`

**Trivial path:** If scope is `trivial` (single-line edits, typo fixes, config value changes), skip Steps 2–4. Go directly to Step 5 with a minimal lug. Use sparingly — if there is any doubt about overlap or fit, run the full protocol.

---

## Step 2: Similarity and Fit Check

**Mandatory before refinement questions and before any lug is created.**

### 2a. Scan Open Lugs

Read active lugs from `WAI-Spoke/lugs/bytype/*/open/` and `*/in_progress/`. For each active lug, assess similarity to the incoming idea's **challenge** and **hypothesis**:

| Similarity Type | Definition | Action |
|----------------|------------|--------|
| **Exact** | Same challenge and same mechanism | Flag as duplicate — present existing lug, ask user to confirm merge or distinguish |
| **Challenge overlap** | Same problem, different proposed solution | Flag as related — competing hypotheses for the same challenge |
| **Hypothesis overlap** | Different framing, same mechanism | Flag — may indicate terminology mismatch or broader opportunity |
| **Dependency** | Incoming idea requires this lug resolved first | Note as blocker |
| **Conflict** | Incoming idea contradicts or replaces this lug | Flag — needs explicit decision before proceeding |

Present any matches. One sentence per match is enough.

### 2b. Scan Existing Skills and Functionality

Check `templates/commands/` and `WAI-Spoke/skills/` for skills that already address any part of the challenge. Also check `WAI-State.json` → `features[]` and `_project_foundation.in_scope[]`.

Assess: **Full coverage** / **Partial coverage** / **Terminology gap**.

### 2c. Scan Signals and Decisions

Filter active lugs for `type: "signal"` with impact >= 7. Check whether any captured decision already resolved the challenge, ruled out the mechanism, or established a precedent.

### 2d. Terminology Reconciliation

The most common fitting problem is terminology drift. Surface mismatches explicitly before proceeding:
> "You called this [user term] — the system uses [system term] for this. Are you extending that, or describing something different?"

See `wai-improve-reference.md` for terminology examples.

### 2e. Produce Fit Report

After scanning, present a fit report before asking refinement questions. See `wai-improve-reference.md` for the fit report template.

**Fit classifications:**
- `net_new` — no meaningful overlap; proceed as new idea
- `extends` — builds on existing lug or skill; reference it in `related_lugs`
- `supersedes` — replaces existing lug; old lug should be reconciled on implementation
- `conflicts` — contradicts open lug or prior decision; resolve before proceeding
- `duplicate` — already tracked; redirect to existing lug

If `duplicate` or `conflicts`: **stop**. Do not proceed until user acknowledges and decides.

---

## Step 3: Refinement Questions

After intake and fit check, ask refinement questions grounded in both spoke context (Step 0) and fit findings (Step 2).

If fit check found overlaps, address those first:
- "How is this different from `{overlapping lug}`?"
- "Does this replace `{skill}` entirely, or work alongside it?"
- "You used `{user term}` — does that map to `{system term}`, or is it something new?"

Look for tensions with foundation: constraints, current phase, philosophy, stack.

**Standard fallback questions** (if foundation is thin or fit check found nothing):
1. Is the challenge currently blocking anything active?
2. What would be measurably different after this is implemented?
3. Does this need to work across spokes, or just here?

Ask at most 3 questions at a time. The answers may change the fit classification.

---

## Step 3b: Challenge Matching

After Step 3, the challenge statement is in canonical form. Match it against `WAI-Spoke/WAI-Challenges.jsonl` to link to an existing problem or create a new one. If the file doesn't exist, create it as empty before proceeding.

**Normalization pipeline** (apply before comparison):
1. Lowercase
2. Strip punctuation
3. Tokenize on whitespace
4. Remove stopwords (same list as `historian.yaml` → `pattern_scan.algorithm`)
5. Apply Porter stemming (`detect`, `detecting`, `detection` → `detect`)

**Matching:** Jaccard similarity between normalized token sets:
```
similarity = |tokens(A) ∩ tokens(B)| / |tokens(A) ∪ tokens(B)|
```
Threshold: **0.5**

**If match found (similarity >= 0.5):**
> This challenge overlaps with `{i}`: "{statement}" (similarity: {score}). Same problem? [enter=yes / type correction]

On confirmation: set `challenge_id` = existing challenge `i`. Append override entry to `WAI-Challenges.jsonl` adding this idea to `related_lugs`.

**If no match:** Propose new challenge entry with slug (3–5 meaningful words, hyphens, lowercase). On accept: append to `WAI-Challenges.jsonl`, set `challenge_id`. After Step 5, update `first_seen_in`.

**Slug example:** `"Recurring friction across sessions is invisible"` → `chal-recurring-friction-invisible`

---

## Step 4: Evaluation and Scoring

Score on four dimensions using spoke-specific translations from Step 0c. Each dimension: **low / medium / high**.

### 1. Velocity Lift
How much does this speed up the human-AI collaboration cycle? Calibrated against the spoke-specific definition from Step 0c.

### 2. Implementation Cost
- **Low** — additive single-file change, no migration (1 session)
- **Medium** — new skill + type + tests, or cross-file protocol change (2–3 sessions)
- **High** — architectural change, migration required, or multiple spokes affected (epic-level)

### 3. System Fit
- **Aligned** — extends existing patterns naturally
- **Neutral** — independent of core patterns
- **Tension** — introduces complexity or conflicts with stated boundaries

Use the spoke-specific definition. Reflect any tension flagged in Step 2.

### 4. Generality
- **All spokes** — improves every project using Wheelwright
- **Hub** — improves cross-spoke coordination
- **Framework** — improves the authoring/distribution workflow
- **Single spoke** — local improvement only

---

## Priority Classification

Base priority from velocity + cost + fit:

| Velocity | Cost | Fit | → Base Priority |
|----------|------|-----|-----------------|
| High | Low | Aligned | **P0 — Do next** |
| High | Low | Neutral/Tension | **P1 — Do soon, watch fit** |
| High | Medium | Aligned | **P1 — Plan carefully** |
| High | High | Aligned | **P2 — Epic needed** |
| Medium | Low | Aligned | **P2 — Quick win** |
| Medium | Medium | Any | **P3 — Backlog** |
| Low | Any | Any | **P4 — Defer** |
| Any | Any | Tension | **⚠ flag: revisit design before starting** |

**Phase Adjustment:** Adjust one tier based on `context.current_phase`:

| Phase | Adjustment |
|-------|------------|
| `early-build` / `active-development` | +1 tier if `velocity: high` |
| `stabilization` / `hardening` | −1 tier if `system_fit: neutral` or `tension` |
| `scale-out` / `distribution` | +1 tier if `generality: all-spokes` or `hub` |
| `maintenance` | −1 tier if `implementation_cost: high` |

One adjustment only, no stacking. Show: `P{N} (base P{N}, adjusted for {phase})`.

**Override Rules:**
- `scope: schema` or `protocol` → require design discussion before starting
- `generality: all-spokes` + P0/P1 → candidate for teaching file distribution
- `system_fit: tension` → no start without explicit design discussion
- `fit_classification: conflicts` → no start until conflict resolved
- Foundation incomplete → no idea promoted above P3

---

## Step 5: Output as Idea Lug

Every fully-processed idea becomes a lug. **Required fields proving full processing:**
- `spoke_context_loaded: true` — Step 0 completed
- `fit_classification` — Step 2 completed
- `challenge` and `hypothesis` — Step 1 completed
- `challenge_id` — Step 3b completed
- `priority` — Step 4 completed

A lug missing any of these was not fully processed. Treat as `s: raw` regardless.

**Status lifecycle:**
```
raw → evaluating → proposed → approved → (epic created)
                ↓                      ↘ deferred / discarded / merged / supersedes
             reframed
                ↓
             proposed
```

See `wai-improve-reference.md` for full idea lug JSON template.

---

## Step 6: Promotion Protocol — Proposed → Approved

Run when the user says "let's move this forward" or when the idea reaches P0/P1 and the user wants to act. Do not run speculatively.

### 6a. Draft PEV Fields

A build-ready lug needs three fields not in an idea lug:
- **Perceive** — specific files + fields + conditions (not "relevant files")
- **Execute** — numbered, concrete steps; one action each; no vague verbs
- **Verify** — checkable conditions; prefer grep/diff/test over "looks right"

Draft in conversation. Do not invent specifics the user hasn't confirmed.

### 6b. Unresolved Question Check

Confirm nothing from prior steps is open: no unresolved conflicts, all refinement questions answered, terminology reconciled, hypothesis is specific.

### 6c. Dogfood Check

Read the drafted PEV fields as a naive agent would — no chat history, no prior sessions, only the lug.

- **Perceive:** Does each item name a specific file and condition? Can an agent locate the starting point cold?
- **Execute:** Are steps numbered, single-action, with explicit file paths and no vague verbs?
- **Verify:** Is each item a checkable true/false condition? No "works correctly" or "looks right"?

Any fail → rewrite that field before proceeding.

### 6d. Complexity Check

Does it touch 2+ files or require 6+ steps? If yes: note in the lug that `/wai-complexity-gate` should run at implementation start.

### 6e. User Approval

Present the final lug fields for user sign-off. On approval: update `s` from `proposed` to `approved`, add PEV fields. See `wai-improve-reference.md` for the approval presentation template.

### 6f. What Comes Next

A `s: approved` idea lug is the input to an implementation session. In the next session: read the idea lug → run complexity gate if triggered → create epic/task from it → close idea lug (`s: c`, `superseded_by: epic-id`). The idea lug is the record of why the epic exists.

---

## Backlog Review Mode

1. Load spoke context (Step 0)
2. Read all `ty: "idea"` lugs from `bytype/other/open/` — de-duplicate by ID
3. For each idea: re-run Step 2 (fit check) against current state
4. Group: **Ready to promote** / **Needs reframe** / **Merge candidates** / **Now duplicate** / **Recommend discard**

Present the grouped summary. Let the user choose which group to tackle first.

See `wai-improve-reference.md` for the backlog review output template.

---

## Reframe Protocol

For any idea where hypothesis is stale but challenge is still valid:
1. Preserve challenge verbatim in `challenge`
2. Move old hypothesis to `prior_hypothesis`
3. Write new hypothesis based on current system state
4. Add `reframe_notes` — one sentence on what changed
5. Re-run Step 2 with the new hypothesis

---

## Agent-Initiated Ideas

Agents surface ideas when observing repeated manual steps, workarounds used more than once, gaps between what a skill says and what works, or patterns across session tracks.

Surface as: > "I noticed [observation]. Challenge: [challenge]. Hypothesis: [hypothesis]. Worth running through /wai-improve?"

Agent does NOT create the lug without user acknowledgment.

---

## Distribution Note

This skill is distributed to all spokes. When it runs on a spoke, it reads **that spoke's** foundation, open lugs, skills, and signals — not framework-specific assumptions. Quality of output scales with quality of foundation.

---

## Related Skills

- `/wai-foundation` — required before evaluating ideas on an unfamiliar project
- `/wai-lug-schema` — lug schema and authoring rules
- `/wai-complexity-gate` — planning gate before implementation begins
- `/wai-stewardship-guard` — scope drift detection during implementation

---

*Fitting is the work. An idea that hasn't been fit into the current system is just a wish.*

<!-- pipeline-verified-2026-03-25: skill-thrift-v1 applied -->
