# WAI Improve — Reference
> Fast path: load `wai-improve-reference-slim.md` first. Load this file only when deep protocol is needed.

**Companion to `wai-improve.md`.** Contains templates, examples, and verbose specs. Load on-demand — not loaded at wakeup.

---

## Fit Report Template (Step 2e)

```
### Fit Report — {idea title}

**Existing lug overlap:**
- {lug id} "{title}": {similarity type} — {one sentence on what overlaps}
  (none found)

**Existing functionality overlap:**
- {skill/feature}: {full/partial coverage} — {what it already handles}
  (none found)

**Signal/decision conflicts:**
- {signal summary}: {how it relates}
  (none found)

**Terminology notes:**
- "{user term}" → system calls this "{system term}"
  (none found)

**Fit classification:** net_new | extends | supersedes | conflicts | duplicate
```

---

## Terminology Reconciliation Examples

| User's term | System's existing term | Relationship |
|-------------|----------------------|--------------|
| "incoming processing" | `wai` (Step 3a: teaching discovery) / incoming protocol | Same concept |
| "idea queue" | `ty: "idea"` lugs | Same concept |
| "project memory" | foundation lug + WAI-State.json | Partial — foundation is the structured part |
| "send to another project" | `/wai (Step 9b: auto-teach on closeout)` outgoing delivery | Same concept |

---

## Idea Lug — Full JSON Template (Step 5)

```json
{
  "i": "idea-{slug}-v{N}",
  "ty": "idea",
  "t": "Short title — in system terminology after reconciliation",
  "s": "proposed",
  "ca": "ISO-8601",
  "gb": "user | model-id",
  "challenge": "What problem this solves — the stable part",
  "hypothesis": "Proposed mechanism — the testable part",
  "prior_hypothesis": "Original hypothesis if reframed (omit if not reframed)",
  "reframe_notes": "Why hypothesis changed (omit if not reframed)",
  "origin": "user | agent | signal | backlog",
  "challenge_id": "chal-{slug} — from WAI-Challenges.jsonl. Required on fully-processed ideas.",
  "scope": "skill | protocol | schema | tooling | multi",
  "spoke_context_loaded": true,
  "fit_classification": "net_new | extends | supersedes | conflicts | duplicate",
  "related_lugs": ["lug-ids found in fit check"],
  "terminology_reconciled": ["user term → system term if any mismatches resolved"],
  "scores": {
    "velocity_lift": "high | medium | low",
    "implementation_cost": "low | medium | high",
    "system_fit": "aligned | neutral | tension",
    "generality": "all-spokes | hub | framework | single-spoke"
  },
  "priority": "P0 | P1 | P2 | P3 | P4",
  "next_step": "discuss | prototype | epic | defer | discard",
  "agent_framing": "Agent's sharpened statement after discussion (if improved)",
  "_behavior_directive": {
    "what_this_is": "A structured improvement idea. Evaluate before acting.",
    "what_this_is_NOT": "An instruction to implement. Requires explicit user direction."
  }
}
```

**Required fields that prove full processing:** `spoke_context_loaded`, `fit_classification`, `challenge`, `hypothesis`, `challenge_id`, `priority`.

---

## Step 6e — User Approval Presentation Template

```
### Ready for approval — idea-{slug}-v{N}

**Challenge:** {challenge}
**Hypothesis:** {hypothesis}
**Perceive:** {perceive}
**Execute:**
  1. {step}
  2. {step}
  ...
**Verify:** {verify items}

**Priority:** P{N}
**Scope:** {scope}
**Fit:** {fit_classification}
**Related:** {related_lugs or none}

Approve? (yes to promote / adjust to revise / defer to backlog)
```

---

## Backlog Review Output Template

```
### Idea Backlog — {project name}

Context loaded: {one_liner}
Current phase: {phase}

**Ready to promote (challenge valid, fit clean, hypothesis current):**
- idea-X: {title} — P{N}

**Needs reframe (challenge valid, hypothesis stale):**
- idea-Y: {title} — {what changed}

**Merge candidates (overlapping challenges):**
- idea-A + idea-B — {shared challenge}

**Now duplicate (system already does this):**
- idea-Z: {title} — covered by {skill/lug}

**Recommend discard (challenge no longer relevant):**
- idea-W: {title} — {why}
```

---

## Step 6c Dogfood Check — Detailed Audit Criteria

### Perceive Audit

- Does each item name a specific file or directory? (not "relevant files")
- Does each item name a specific field, line, or condition? (not "check the state")
- Could an agent locate the starting point cold, with no prior context?

→ **Pass:** all items are unambiguously locatable.
→ **Fail:** any item requires guessing or inference. Rewrite that item.

### Execute Audit

- Are steps numbered and ordered?
- Does each step contain exactly one action? (not "update and verify" in one step)
- Are all file paths explicit — absolute or relative to a named root?
- Are vague verbs absent? ("update" → "replace line N with X", "handle" → specific action)
- Does each step that depends on a prior step say so explicitly?

→ **Pass:** an agent can execute step N knowing only steps 1..N-1 and the lug.
→ **Fail:** any step requires guessing a value, path, or action. Rewrite that step.

### Verify Audit

- Is each item a checkable condition, not a feeling?
- Does each item specify what to check and what the expected result is?
- Are "works correctly", "looks right", "seems complete" absent?

→ **Pass:** all items can be confirmed true/false with no prior context.
→ **Fail:** any item requires judgment or context not in the lug. Replace it.

**Outcome:** All three pass → proceed to 6d. Any fail → fix and re-audit that section only.

---

## Challenge→Hypothesis→Lug Worked Example

**User input:** "Sometimes agents apply teachings without fully reading what they do."

**Challenge (extracted):** Agents lose track of which teachings they've already applied.

**Hypothesis:** "If we add a processed/ directory and use filename matching, agents will avoid re-applying known teachings."

**After fit check:** `wai` Step 5 already has `seed/ingest/processed/` — this is `extends`, not `net_new`.

**After reframe:** "If we add a lug-based receipt record when teachings are applied, agents will have durable proof of adoption across sessions." → `fit_classification: extends`, `related_lugs: ["wai.md Step 5"]`

**Result:** `priority: P2` (Medium velocity, Low cost, Aligned fit).

---

## Foundation Completeness Check — Signal Table (Step 0b)

| Signal | What It Means |
|--------|--------------|
| `identity.one_liner` is null or generic | Cannot evaluate fit or velocity — ask user |
| `boundaries.in_scope` is empty | Cannot evaluate system fit |
| `boundaries.constraints` is empty | Cannot evaluate cost or risk |
| `context.current_phase` is null | Cannot weight urgency |
| No foundation lug exists at all | **Stop. Run `/wai-foundation` first.** |

---

## Similarity Type Definitions (Step 2a)

| Similarity Type | Definition | Action |
|----------------|------------|--------|
| **Exact** | Same challenge and same mechanism | Flag as duplicate — present existing lug, ask user to confirm merge or distinguish |
| **Challenge overlap** | Same problem, different proposed solution | Flag as related — competing hypotheses for the same challenge |
| **Hypothesis overlap** | Different framing, same mechanism | Flag — may indicate terminology mismatch or broader opportunity |
| **Dependency** | Incoming idea requires this lug resolved first | Note as blocker |
| **Conflict** | Incoming idea contradicts or replaces this lug | Flag — needs explicit decision before proceeding |

---

## Challenge Matching — Normalization Pipeline (Step 3b)

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

**If no match:** Propose new challenge entry with slug (3-5 meaningful words, hyphens, lowercase). On accept: append to `WAI-Challenges.jsonl`, set `challenge_id`. After Step 5, update `first_seen_in`.

**Slug example:** `"Recurring friction across sessions is invisible"` → `chal-recurring-friction-invisible`

---

## Priority Matrix (Step 4)

| Velocity | Cost | Fit | Base Priority |
|----------|------|-----|---------------|
| High | Low | Aligned | **P0 — Do next** |
| High | Low | Neutral/Tension | **P1 — Do soon, watch fit** |
| High | Medium | Aligned | **P1 — Plan carefully** |
| High | High | Aligned | **P2 — Epic needed** |
| Medium | Low | Aligned | **P2 — Quick win** |
| Medium | Medium | Any | **P3 — Backlog** |
| Low | Any | Any | **P4 — Defer** |
| Any | Any | Tension | **Flag: revisit design before starting** |

### Phase Adjustment

Adjust one tier based on `context.current_phase` (one adjustment only, no stacking):

| Phase | Adjustment |
|-------|------------|
| `early-build` / `active-development` | +1 tier if `velocity: high` |
| `stabilization` / `hardening` | -1 tier if `system_fit: neutral` or `tension` |
| `scale-out` / `distribution` | +1 tier if `generality: all-spokes` or `hub` |
| `maintenance` | -1 tier if `implementation_cost: high` |

Show: `P{N} (base P{N}, adjusted for {phase})`.

---

## Status Lifecycle (Step 5)

```
raw → evaluating → proposed → approved → (epic created)
                ↓                      ↘ deferred / discarded / merged / supersedes
             reframed
                ↓
             proposed
```
