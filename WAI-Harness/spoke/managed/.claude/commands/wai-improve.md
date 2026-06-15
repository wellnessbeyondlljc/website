# WAI Improve
> Fast path: load `wai-improve-slim.md` first. Load this file only when deep protocol is needed.

**Improvement Idea Protocol — capture, evaluate, and prioritize system improvement ideas in the context of this spoke.**

- **Nodes:** spoke, hub | **Exposure:** spoke.chat:local
- **Trigger:** User submits an idea, agent surfaces a pattern, or `/wai-improve` is called directly

**Core Principle:** Separate the challenge (problem worth solving) from the hypothesis (one possible solution). Old ideas almost always have a valid challenge — only the hypothesis goes stale. Never discard the challenge when the hypothesis is outdated. Reframe. Load context before evaluating.

---

## Execution Flow

```
Step 0: Load spoke context (foundation, boundaries, phase)
Step 1: Intake (challenge, hypothesis, origin, scope)
Step 2: Similarity and fit check ← must complete before refinement or scoring
Step 3: Refinement questions (informed by Steps 0 + 2)
Step 3b: Challenge matching (link → WAI-Challenges.jsonl)
Step 4: Evaluation and scoring
Step 5: Output as idea lug (or merge/supersede/discard decision)
```

Steps 2 and 3 are the fitting work. A lug that skips these steps is not fully processed.

---

## Step 0: Load Spoke Context (Required)

**0a.** Read `WAI-Spoke/WAI-State.json`: `_project_foundation.identity.one_liner`, `success_looks_like`, `boundaries.*`, `philosophy.core_principle`, `approach.stack_or_tools`, `context.current_phase`. Also check `lugs/bytype/other/open/` for foundation lugs.

**0b.** Foundation completeness check — if critical fields are missing (one_liner, in_scope, constraints, current_phase), ask rather than inventing. No foundation lug at all → **stop, run `/wai-foundation` first.** See `wai-improve-reference.md` for the completeness signal table.

**0c.** Build scoring context — write a one-line spoke-specific definition of each dimension (velocity lift, system fit, implementation cost, generality). Show to user at start of backlog sessions.

---

## Step 1: Intake

Extract or prompt for:

- **Challenge** — the stable part. What breaks, slows, or is missing? If vague: "What breaks or feels wrong without this?"
- **Hypothesis** — format: "If we [do X], then [outcome Y] because [reason Z]"
- **Origin** — `user` / `agent` / `signal` / `backlog`
- **Scope** — `skill` / `protocol` / `schema` / `tooling` / `multi` / `trivial`

**Trivial path:** If scope is `trivial` (single-line edits, typo fixes), skip Steps 2-4 and go directly to Step 5 with a minimal lug.

---

## Step 2: Similarity and Fit Check

**Mandatory before refinement questions and before any lug is created.**

**2a.** Scan open lugs (`bytype/*/open/` and `*/in_progress/`). Assess similarity to incoming challenge and hypothesis. Classifications: Exact, Challenge overlap, Hypothesis overlap, Dependency, Conflict. Present any matches (one sentence each). See `wai-improve-reference.md` for similarity type definitions.

**2b.** Scan `templates/commands/` and `WAI-Spoke/skills/` for existing coverage. Assess: Full / Partial / Terminology gap.

**2c.** Scan active signal lugs (impact >= 7) for decisions that already resolved the challenge.

**2d.** Surface terminology mismatches explicitly: > "You called this [user term] — the system uses [system term]. Extending that, or something different?" See reference for examples.

**2e.** Produce fit report. Classifications: `net_new` / `extends` / `supersedes` / `conflicts` / `duplicate`. If `duplicate` or `conflicts`: **stop** until user acknowledges. See `wai-improve-reference.md` for fit report template.

---

## Step 3: Refinement Questions

After intake and fit check, ask questions grounded in spoke context and fit findings. Address overlaps first. Look for tensions with foundation. Ask at most 3 questions at a time.

**Fallback questions** (if foundation thin or fit check found nothing):
1. Is the challenge currently blocking anything active?
2. What would be measurably different after implementation?
3. Does this need to work across spokes, or just here?

---

## Step 3b: Challenge Matching

Match the canonical challenge statement against `WAI-Challenges.jsonl`. Use normalized token comparison (Jaccard similarity, threshold 0.5). On match: set `challenge_id` to existing entry. No match: propose new challenge slug (3-5 words, hyphens, lowercase). See `wai-improve-reference.md` for normalization pipeline and matching details.

---

## Step 4: Evaluation and Scoring

Score on four dimensions using spoke-specific definitions from Step 0c. Each: **low / medium / high**.

1. **Velocity Lift** — how much does this speed up human-AI collaboration?
2. **Implementation Cost** — Low (1 session, single-file) / Medium (2-3 sessions, cross-file) / High (epic-level, migration)
3. **System Fit** — Aligned / Neutral / Tension (reflect Step 2 findings)
4. **Generality** — All spokes / Hub / Framework / Single spoke

## Priority Classification

Derive priority from velocity + cost + fit. See `wai-improve-reference.md` for the full priority matrix and phase adjustment table.

**Key rules:** High velocity + Low cost + Aligned = P0. Low velocity = P4. Tension = flag for design discussion. Foundation incomplete = ceiling P3.

**Override rules:** `scope: schema|protocol` → design discussion required. `generality: all-spokes` + P0/P1 → teaching file candidate. `fit_classification: conflicts` → blocked until resolved.

---

## Step 5: Output as Idea Lug

**Required fields proving full processing:** `spoke_context_loaded: true`, `fit_classification`, `challenge`, `hypothesis`, `challenge_id`, `priority`. Missing any → treat as `s: raw`.

Status lifecycle: `raw → evaluating → proposed → approved → (epic created)`, with branches to `reframed`, `deferred`, `discarded`, `merged`, `supersedes`. See `wai-improve-reference.md` for full JSON template.

---

## Step 6: Promotion Protocol — Proposed to Approved

Run when user says "let's move this forward" or idea reaches P0/P1 and user wants to act. Not speculative.

**6a.** Draft PEV fields — Perceive (specific files + conditions), Execute (numbered concrete steps), Verify (checkable true/false conditions). Draft in conversation.

**6b.** Unresolved question check — confirm no open conflicts, all questions answered, terminology reconciled.

**6c.** Dogfood check — read PEV as a naive agent. Perceive items must name specific files. Execute steps must be single-action with explicit paths. Verify items must be checkable. Any fail → rewrite. See `wai-improve-reference.md` for detailed audit criteria.

**6d.** Complexity check — 2+ files or 6+ steps → note that `/wai-complexity-gate` should run at implementation start.

**6e.** Present for user approval. On approval: `s: proposed` → `s: approved`, add PEV fields. See reference for presentation template.

**6f.** An approved idea lug is input to an implementation session: read lug → complexity gate → create epic/task → close idea lug (`s: c`, `superseded_by: epic-id`).

---

## Backlog Review Mode

Load context (Step 0) → read all `ty: "idea"` lugs from `bytype/other/open/` → re-run fit check (Step 2) → group into: Ready to promote / Needs reframe / Merge candidates / Now duplicate / Recommend discard. Present grouped summary. See reference for output template.

## Reframe Protocol

For ideas where hypothesis is stale but challenge is valid: preserve challenge, move old hypothesis to `prior_hypothesis`, write new hypothesis, add `reframe_notes`, re-run Step 2.

## Agent-Initiated Ideas

Surface as: > "I noticed [observation]. Challenge: [X]. Hypothesis: [Y]. Worth running through /wai-improve?" Agent does NOT create lug without user acknowledgment.

---

**Related:** `/wai-foundation` (required for unfamiliar projects) | `/wai-lug-schema` | `/wai-complexity-gate` | `/wai-stewardship-guard`

*Distributed to all spokes — reads that spoke's foundation, lugs, and skills. Fitting is the work.*

<!-- pipeline-verified-2026-03-25: skill-thrift-v1 applied -->
