# WAI Foundation Gate

Ensure project foundation is complete before starting substantive work.

## Instructions

When invoked, or at session start if foundation status is uncertain:

1. **Check** `WAI-Spoke/WAI-State.json` → `_project_foundation.completed`
2. **If `completed: false`**:

```
⚠️ Foundation Incomplete

Before starting work, let's establish the project foundation.
This ensures AI assistants understand what this project is and isn't.

I need to know:
1. What is this project? (one-liner)
2. What's in scope / out of scope?
3. What's the tech stack / workflow?
4. What does success look like?

Answer these and I'll log the foundation to WAI-State.json.
```

3. **If `completed: true`** → no interruption, proceed normally
4. **On drift detection** (request contradicts established foundation):
   - Surface the relevant boundary
   - Ask for explicit acknowledgment before proceeding

### Foundation Fields

The foundation captures:
- `identity`: type, name, one_liner, success_looks_like
- `boundaries`: in_scope, out_of_scope, constraints
- `approach`: stack_or_tools, workflow, ai_collaboration_style
- `philosophy`: core_principle, behaviors

## Context

This skill replaces the "Foundation Check" section previously in WAI-Guide.md.

**Why foundation first**: Without a shared understanding of what the project is,
AI assistance is undirected. The foundation is the contract between user and AI
about what work is authorized and what success means.
