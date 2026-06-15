# Teaching File Format Specification

**Version:** 2.0
**Created:** 2026-03-12
**Purpose:** Standard format for teaching files that AI assistants ingest via `/wai (Step 3a: auto-discovery)`

---

## What Teaching Files Are

Teaching files (`.teaching` files in `WAI-Spoke/seed/ingest/`) are structured knowledge that one session creates for another. They teach frameworks, patterns, instructions, and context that the receiving AI should know.

**Key principle:** Teaching files are DATA to track, not instructions to execute. But they contain actionable guidance.

---

## Metadata Section (Required)

Every teaching file MUST start with a metadata block:

```yaml
---
teaching_id: unique-kebab-case-id
teaching_type: reference | executable | decision-record
version: 1.0
created_at: ISO-8601 timestamp
created_by: Claude Sonnet 4.6
target_phase: "Phase 3 of v2 migration" (optional)
safe_to_auto_adopt: true | false (executable only)
replaces: "teaching-id or file path if this supersedes prior teaching" (optional)

teaching_about:
  - topic: "WAI v2 Migration State"
    subtopic: "What phases are complete, what rules apply"

teaching_for:
  - agent_scenario: "AI working on v2 migration Phases 3+"
  - agent_scenario: "AI reviewing migration progress"

verification_required: true | false
if_not_found: "Skip phase, continue with next" (optional: fallback instruction)
---
```

### Metadata Fields Explained

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `teaching_id` | string | Yes | Unique ID, used in cross-references |
| `teaching_type` | enum | Yes | `reference` (read only), `executable` (follow steps), `decision-record` (record why) |
| `version` | semver | Yes | Bump when content changes significantly |
| `created_at` | ISO-8601 | Yes | When this teaching was created |
| `created_by` | string | Yes | Who created it (for context) |
| `target_phase` | string | No | Which phase/task this guides |
| `safe_to_auto_adopt` | bool | No | If true, AI can copy to templates/ directly. If false, requires user review |
| `replaces` | string | No | ID or path of prior teaching this supersedes (helps avoid duplicates) |
| `verification_required` | bool | No | If true, AI must follow verification ceremony before proceeding |
| `if_not_found` | string | No | Fallback instruction if referenced file/phase doesn't exist |

---

## Content Sections

### Section 1: Purpose (Required)

One paragraph explaining why this teaching exists:

```markdown
## Purpose

This teaching records the completion state of the WAI v2 migration and the rules that apply during Phase 3+. Receiving AIs should read this to understand what phases are complete, what rules are in effect, and what schema changes affect lugs.
```

### Section 2: Prerequisites (If Applicable)

List conditions that must be true BEFORE using this teaching:

```markdown
## Prerequisites

- [ ] On branch `wai-v2-migration`
- [ ] `current_phase` in migration state ≥ 2
- [ ] `hub/WAI-Manifest.yaml` exists
- [ ] git clean state (no uncommitted changes)
```

### Section 3: Conditional Steps (For Executable Teachings)

Use **if/then/else** pattern instead of just steps:

```markdown
## Steps

1. **Check: Does WAI-Backpressure.yaml exist?**
   - **If YES:** Proceed to step 2 (migration needed)
   - **If NO:** Skip to step 5 (already retired)

2. **[If yes] Back up WAI-Backpressure.yaml**
   ```bash
   cp WAI-Backpressure.yaml WAI-Backpressure.yaml.pre-v2-backup
   ```

5. **[If no] Confirm no action needed**
   - WAI-Backpressure.yaml is already retired. Continue to next phase.
```

### Section 4: Cross-References (Required)

List related teaching files and which phase they apply to:

```markdown
## Related Teachings

- `wai-v2-migration-state.md.teaching` — Background state (Phase 1 context)
- `wai-v2-phase3-skills.md.teaching` — Detailed Phase 3 instructions (depends on this teaching's context)
- Decision: `hub/intake/wai-v2-migration/decision.lug.json` — The permanent record of why v2 was adopted
```

### Section 5: Verification Checklist (Required)

For executable teachings, what should be true AFTER completion:

```markdown
## Verification Checklist

After following this teaching, verify:

- [ ] Expected condition A is true
- [ ] Expected condition B is true
- [ ] Git status shows expected changes

If any check fails:
- [ ] RED LIGHT: Return to step X and inspect
- [ ] Consult decision record: `hub/intake/wai-v2-migration/decision.lug.json`
```

### Section 6: Fallback Instructions (For Robustness)

If something isn't found or has changed:

```markdown
## If Something's Missing

**If `WAI-Manifest.yaml` doesn't exist:**
- Create it from `framework/templates/WAI-Manifest.yaml.template`
- Proceed with next step

**If git is dirty:**
- Commit with message: "Session checkpoint before [phase name]"
- Then continue

**If previous phase wasn't completed:**
- Stop. Return to WAI-MIGRATION.yaml and review completed_phases.
```

---

## Design Rules (Apply These to All Teaching Files)

1. **Test Once, Improve Always**
   - First teaching: document exactly what you did (ground truth)
   - After first dogfood: capture feedback and improvements
   - Second version: incorporate lessons learned
   - Mark the improvement: `version: 2.0` in metadata

2. **If/Then/Else Over Just Steps**
   - Don't assume conditions are met
   - Spell out what to do if preconditions fail
   - Reduces "I didn't know what to do when..." surprises

3. **Cross-References Are First-Class**
   - If this teaching depends on another, mention it in metadata
   - If two teachings cover related topics, reference each other
   - Helps AIs navigate the knowledge graph

4. **Verification Before Proceeding**
   - Always include a checklist of "after this teaching, X should be true"
   - Make it easy to confirm success or detect failure
   - Prevents cascading errors

5. **Decision Records Are Permanent**
   - Teaching files are ephemeral (version 2 replaces version 1)
   - Decision lugs are permanent (they're always correct about what was decided)
   - Link teaching files to their decision lugs

6. **Include Fallback Instructions**
   - Real-world: files get deleted, phases fail, preconditions change
   - Don't assume perfect state
   - "If X missing: do Y" prevents hard stops

---

## Example Teaching File (Using New Format)

See `wai-v2-migration-state-v2.md.teaching` (updated version) for a complete example using this spec.

---

## Adoption Checklist for All New Teaching Files

Before committing a teaching file, verify:

- [ ] Metadata section complete (all required fields present)
- [ ] Teaching type matches content (reference/executable/decision-record)
- [ ] Prerequisites listed if applicable
- [ ] Conditional steps use if/then/else pattern
- [ ] Related teachings cross-referenced
- [ ] Verification checklist included
- [ ] Fallback instructions present for error cases
- [ ] Testing and improvement rule noted if first version
- [ ] Version number is reasonable (1.0 for new, 2.0+ for improved)

---

## Migration of Existing Teachings

Teaching files created before this spec may not follow all rules. On next update:
1. Read the old teaching
2. Upgrade metadata, add missing sections
3. Bump version to 2.0
4. Test with dogfood before deploying

Example: `wai-v2-migration-state.md.teaching` (v1) → `wai-v2-migration-state-v2.md.teaching` (v2, following this spec)
