# WAI Improve — Reference

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
