# WAI Principles — Reference

**Companion to wai-principles.md.** Load on-demand.

---

## P9: Intuitive Design — Full Specification

### Requirements

Every WAI skill, command, or component must include:

| Section | Purpose |
|---------|---------|
| **When to Use** | Trigger conditions (what activates this?) |
| **Prerequisites** | What must be true before running |
| **What It Does** | Clear steps, no ambiguity |
| **Follow-ons** | What typically comes next |
| **Use Cases** | Concrete examples of when to use |

### Why

- Agents should know **when and why** to activate each component
- No guessing, no memorization required
- System improves itself by being self-documenting

### Template

Every WAI skill should follow this structure:

```markdown
# [Skill Name]

**[One-line purpose]**

## When to Use
- [Trigger condition 1]
- [Trigger condition 2]

## Prerequisites
- [Required state/files]
- [Prior actions needed]

## What It Does
1. [Step 1]
2. [Step 2]
...

## Follow-ons
- [What typically comes next]
- [Related commands]

## Use Cases

**Use Case 1: [Name]**
- Situation: [context]
- Action: [what to do]
- Result: [expected outcome]

**Use Case 2: [Name]**
- Situation: [context]
- Action: [what to do]
- Result: [expected outcome]
```

### Self-Improvement

When a component is unclear or frequently misused:
1. Identify the confusion point
2. Update the component with clearer triggers/prerequisites
3. Add a use case covering the edge case
4. The system improves itself through use

---

## P10: Autonomy — Extended Guidance

The user has granted permission for routine operations. Do not ask for confirmation before running standard commands (git status, git add, python3, bash scripts, file reads). Proceed and report results.

**Pause only for:**
- Irreversible destructive actions (rm -rf, force push, drop database)
- Actions that affect shared systems outside the local repo
- Explicit user instruction to confirm before proceeding

**Never chain multiple confirmations.** If a sequence of safe commands is needed, run them all and show results together.

**Source:** User prerogative — expressed preference for uninterrupted autonomous execution of trusted operations.

---

## P11: Lug-First Memory — Extended Guidance

Lugs are JSONL records in `WAI-Spoke/lugs/active/WAI-Lugs-active.jsonl` (active) or individual files in `WAI-Spoke/lugs/{type}/` (archived). The active lugs file is the only storage the wakeup protocol reads at session start. When a session ends or is interrupted, lugs survive. Everything else is gone.

**Claude Code Task tools (TaskCreate, etc.) do not survive session ends.** They are not read on wakeup and are invisible to any future agent or tool.

**Standalone `.md` files are not indexed at wakeup.** They require knowing they exist to find them. They go stale. They are not recoverable without manual search.

**Put these in lugs, not tasks or scratch files:**
- Work to be done (intent, scope, acceptance criteria)
- Decisions and rationale
- Progress and handoff state
- Prompts for sub-agents (`workflow.subagent_prompt`)
- Open questions and blockers

**When to apply this:** Any time you are about to call `TaskCreate`, write a scratch `.md` file, or hold state "in your head" across a planned multi-step operation — stop. Put it in a lug instead.

**Minimal example — work-in-progress lug with embedded subagent prompt:**
```json
{
  "id": "work-my-feature-20260322",
  "type": "work",
  "title": "My feature implementation",
  "status": "in-progress",
  "workflow": {
    "subagent_prompt": "You are implementing X. Context: ... Task: ... Acceptance criteria: ...",
    "completed_steps": ["step 1", "step 2"],
    "next_step": "step 3"
  }
}
```
If this session ends now, the next agent reads this lug on wakeup and knows exactly where to resume. A `TaskCreate` entry or scratch file would be gone.

**Demonstrated:** A subagent dispatch prompt was fully recovered after session interruption because it was stored in `workflow.subagent_prompt` on a lug. The next agent found it cold, reproduced it, and resumed work. The equivalent stored in a Task would have been unrecoverable.
