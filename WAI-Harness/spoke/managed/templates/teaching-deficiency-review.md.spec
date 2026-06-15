# Teaching File Quality Gate: Deficiency Review Process

**Version:** 1.0
**Purpose:** Formal process for testing teaching files BEFORE deployment to spokes. Creates permanent record of deficiencies for spec improvement.

---

## Philosophy

Teaching files are not validated by their creator. They are validated by a **cold reviewer**—an AI that:
1. Has not seen the teaching file before
2. Does not know you just created it
3. Is asked only to **review, not implement**
4. Submits deficiencies back to the framework as Lugs

This process:
- Finds blindspots the creator missed
- Tracks deficiencies as permanent Lugs
- Uses those Lugs to improve the teaching-file.spec.md
- Prevents low-quality teachings from reaching spokes

---

## The Process

### Phase 1: Create Teaching File v1.0

Write the teaching file following teaching-file.spec.md. Focus on:
- Accurate metadata
- Clear purpose and prerequisites
- Conditional steps where applicable
- Fallback instructions

Do NOT overthink perfection. v1.0 is ground truth, not polish.

### Phase 2: Cold Review (Deficiency Discovery)

Bring in a fresh AI (one that hasn't seen the teaching) and ask:

```
Review this teaching file WITHOUT IMPLEMENTING IT.

Your job is NOT to execute the steps, but to tell me:
1. Do you have enough information to understand what this teaching does?
2. Are all prerequisites clear? Would you know if they're met?
3. Are there steps where you'd be confused about what to do?
4. If something fails, would you know how to recover?
5. Are there terms used that are never defined?
6. Are there references to files/tools that might not exist?
7. Is the verification checklist sufficient to confirm success?

For each deficiency: note the location, the issue, and what info is missing.
```

### Phase 3: Create Deficiency Lugs

For each deficiency the reviewer found, create a Lug:

```json
{
  "id": "deficiency-{teaching-id}-{number}",
  "type": "deficiency",
  "title": "Teaching file {teaching-id}: Missing {aspect}",
  "description": "Cold reviewer found: {deficiency description}",
  "status": "published",
  "impact": {1-5, depending on severity},
  "created_by": "Teaching Quality Gate",
  "node": "wheelwright/framework",
  "related_teaching": "{teaching-id}",
  "deficiency_type": "missing-definition | unclear-step | undocumented-fallback | undefined-term | missing-example",
  "suggestion": "Reviewer recommended: {specific fix}"
}
```

Append these to `WAI-Spoke/WAI-Lugs.jsonl`.

### Phase 4: Review and Improve to v2.0

Creator reads the deficiency Lugs and:
- Judges which are real issues vs. reviewer misunderstandings
- Creates teaching file v2.0 addressing confirmed deficiencies
- Adds new sections as needed
- Tests the v2.0 against the original deficiency list

### Phase 5: Integrate Learnings into Spec

For recurring deficiencies (found in multiple teaching file reviews), update `teaching-file.spec.md`:
- Add a new required section
- Add an example to the spec
- Bump spec version
- Note the deficiency that prompted this

Example deficiency → spec improvement:
```
Deficiency: Multiple teaching files lacked "Fallback: what if git is dirty?"
→ Improvement: Added "If Something's Missing" section to spec as REQUIRED
```

### Phase 6: Deploy v2.0

Once v2.0 deficiencies are addressed:
- Move v1.0 to `reference/deprecated/`
- Deploy v2.0 as the teaching file spokes receive
- Create a Decision Lug recording what deficiencies were found and how they were fixed

---

## Deficiency Types and Examples

| Type | Example | Severity |
|------|---------|----------|
| missing-definition | Uses term "lug" without explaining what it is | High |
| unclear-step | "Run the migration" without explaining which migration or how | High |
| undocumented-fallback | "If the file doesn't exist..." but no fallback given | Medium |
| undefined-term | References "v2 schema" without explaining the change | Medium |
| missing-example | Says "create a YAML file" without example structure | Medium |
| ambiguous-verification | "Verify it works" without clear success criteria | High |
| implicit-prerequisite | Assumes user knows what "git status --short" means | Low-Medium |

---

## Who Conducts Cold Review?

**Ideal:** An AI from a different project/spoke that isn't familiar with Wheelwright's internal jargon.

**Process:**
1. Conductor sends teaching file + review prompt to a fresh AI
2. Fresh AI submits review without implementation
3. Conductor integrates feedback as deficiency Lugs
4. Creator improves v2.0 based on deficiency Lugs

**Why this works:**
- Fresh AI has beginner's mind
- They're not invested in the teaching (no blind spots from creating it)
- They catch things the creator's brain auto-completes

---

## Metrics: Track Deficiency Trends

After 3+ teaching files:

```python
# Track deficiency types
deficiency_counts = {
  "missing-definition": 5,
  "unclear-step": 3,
  "undocumented-fallback": 4,
  ...
}

# Most common deficiency type → add to spec as required section
# Example: If 4 out of 5 teaching files lack fallback instructions,
# make "If Something's Missing" a REQUIRED section in spec v2.0
```

Use these metrics to evolve the teaching-file.spec.md over time.

---

## Deprecation Strategy

As the framework evolves, teaching files become outdated. Manage this:

1. **Mark as deprecated** when a teaching file is no longer current:
   - Add `# DEPRECATED: See {new-teaching-id} instead` to the file
   - Create Lug: `type: "deprecation"` recording why

2. **Archive v1 versions** in `reference/deprecated/teaching-files/`:
   - Keep them for historical reference
   - Don't serve them to new spokes
   - They teach what was learned and evolved

3. **Track evolution chains**:
   ```yaml
   teaching-id: wai-v2-phase3-skills
   v1.0: wai-v2-phase3-skills.md.teaching (2026-03-12, deprecated)
   v2.0: wai-v2-phase3-skills-v2.md.teaching (2026-03-12, current)
   v3.0: (planned, when v2 feedback arrives)
   ```

---

## Integration with Teaching-File Spec

The deficiency process feeds back into the spec:

**Example Cycle:**
1. Create 3 teaching files following spec v1.0
2. Cold review finds: 5 files missing "What if git is dirty?", 3 files unclear on error recovery
3. Update teaching-file.spec.md:
   - Add "If Something's Missing" as REQUIRED section
   - Add "Error Recovery" as REQUIRED subsection
   - Spec bumps to v1.1
4. Recreate teaching files following spec v1.1
5. Second cold review finds fewer deficiencies
6. Continue improving spec with each cycle

---

## Rapid Iteration + Smart Adaptation

As the framework evolves:

**What Gets Deprecated:**
- Teaching files that covered outdated processes (e.g., "How to use v1 signal format")
- Approaches that didn't work out (archived, not deleted)
- Terminology that changed (tracked in deprecation Lug)

**What Gets Adopted:**
- Patterns that worked across multiple spokes (codified in spec)
- Solutions to common problems (become new required section in spec)
- Successful teaching approaches (replicated in new teaching files)

**How to Track:**
- Deficiency Lugs record what was wrong
- Deprecation Lugs record what changed
- Decision Lugs record what was chosen and why
- The spec version history shows the evolution

---

## Checklist: Before Deploying a Teaching File

- [ ] Created v1.0 following current teaching-file.spec.md
- [ ] Submitted to cold reviewer (fresh AI, no context)
- [ ] Collected deficiency Lugs
- [ ] Reviewed deficiencies, judged severity
- [ ] Created v2.0 addressing confirmed deficiencies
- [ ] Re-tested v2.0 against original deficiency list
- [ ] Integrated learnings into teaching-file.spec (if recurring deficiency)
- [ ] Moved v1.0 to reference/deprecated/ (if significant changes in v2.0)
- [ ] Created Decision Lug recording deficiencies found and how they were fixed
- [ ] Ready to deploy v2.0 to spokes

---

## Example: Phase 9 Documentation Teaching File

Once Phase 9 docs are created:

1. **Create docs v1.0** (ground truth of what you built)
2. **Cold review** from fresh AI: "Can you tell me what the docs are for and how to use them?"
3. **Collect deficiencies** (e.g., "You never define 'Lug,'" "The doc structure isn't clear," etc.)
4. **Create deficiency Lugs** with specific feedback
5. **Improve to v2.0** addressing deficiencies
6. **Update teaching-file.spec** if new patterns emerged
7. **Deploy v2.0** to spokes

---

## Version Control: Teaching File Evolution

Track in git:

```
WAI-Spoke/seed/ingest/processed/
├── wai-v2-migration-state-v2.md.teaching (current)
│
reference/deprecated/teaching-files/
├── wai-v2-migration-state.md.teaching (v1.0, kept for historical reference)

framework/templates/
├── teaching-file.spec.md (v1.0)
├── teaching-file.spec.md.history (tracks spec evolution)
```

And in Lugs:

```json
{
  "id": "decision-teaching-file-wai-v2-phase3-v1-to-v2",
  "type": "decision",
  "title": "Teaching file wai-v2-phase3-skills: upgraded from v1.0 to v2.0",
  "description": "v1.0 cold review found 4 deficiencies. v2.0 addressed all.",
  "deficiencies_found": [
    { "type": "missing-definition", "description": "Lug schema not explained" },
    ...
  ],
  "resolution": "accepted"
}
```

This is permanent record: anyone can see what deficiencies existed and how they were resolved.
