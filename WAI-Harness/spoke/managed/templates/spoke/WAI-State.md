# Wheel State: [PROJECT_NAME]

---

**Wheelwright Framework v1.0**
**Structure:** v1 (WAI-Spoke/ directory)
**Hub:** *Not yet configured - run `WAI hub create` or `WAI hub locate`*

*This wheel uses Wheelwright Framework to maintain perfect context across AI sessions. Wheelwright transforms AI from order-taker to informed, responsible project partner.*

*"We aren't reinventing the wheel - we're evolving it faster than one person ever could."*

---

## Project Foundation

> **IMPORTANT FOR AI ASSISTANTS:**
>
> If the foundation below is incomplete (shows "Not yet defined"), you MUST guide
> the user through establishing it before starting any work. This is not optional.
>
> Ask conversational questions to extract:
> 1. What is this project? (identity)
> 2. What does success look like? (vision)
> 3. What's in scope and out of scope? (boundaries)
> 4. How do we work together? (approach)

### Identity
- **Type:** *Not yet defined*
- **Name:** *Not yet defined*
- **One-liner:** *Not yet defined*
- **Success looks like:** *Not yet defined*

### Boundaries

**In Scope:**
- *To be defined during foundation setup*

**Out of Scope:**
- *To be defined during foundation setup*

**Constraints:**
- *To be defined during foundation setup*

### Approach
- **Stack/Tools:** *To be defined*
- **Workflow:** *To be defined*
- **AI Collaboration:** *To be defined*
- **Review Process:** *To be defined*

---

## Core Philosophy: AI as Responsible Partner

This wheel follows Wheelwright's stewardship philosophy:

> **AI should enable but remain intentful.** When work strays from the
> established foundation, the AI should flag it and require explicit
> acknowledgment before proceeding.

### Stewardship Behaviors
1. **Detect scope drift** - Flag before enabling work outside boundaries
2. **Require acknowledgment** - Direction changes need explicit approval
3. **Complete foundation first** - Guide setup before diving into work
4. **Prefer verification** - "Are you sure?" over silent compliance

### Evolution, Not Drift
When project direction needs to change, it should be **deliberate**:
- AI detects the drift
- Presents options to user
- User explicitly acknowledges the change
- Change is logged in `evolution_log` with rationale

---

## Hub Memory

### Core Objective
*What transformative purpose does this project serve?*

### Problem Statement
*What specific problem are we solving? Who experiences this pain?*

### Key Decisions
1. *[Decision 1 with rationale]*
2. *[Decision 2 with rationale]*

### Established Constraints
- *[Constraint 1]*
- *[Constraint 2]*

### Learned Patterns
- *[Pattern 1: What worked well]*
- *[Pattern 2: What to avoid]*

---

## Active Spokes

### [Spoke Name]
- **Purpose:** [What this spoke does]
- **Current State:** [What it's working on]
- **Outputs:** [What it has produced]

---

## Rolling Context

### Current Phase
*[What phase is the project in?]*

### Recent Progress
- *[Accomplishment 1]*
- *[Accomplishment 2]*

### Next Actions
1. [ ] Complete project foundation
2. [ ] Define initial scope and approach
3. [ ] Begin work with clear context

### Open Questions
- *[Question needing resolution]*

---

## Evolution Log

| Date | Change | Rationale | Acknowledged By |
|------|--------|-----------|-----------------|
| *Date* | Project initialized with Wheelwright | Starting with context persistence | *User* |

---

## Session Log

| Session | Date | Focus | Key Outcomes |
|---------|------|-------|--------------|
| 1 | [Date] | [Topic] | [Outcomes] |

---

## AI Session Instructions

### Before Starting Work
1. Read `WAI-Guide.md` for current policies
2. Check `_project_foundation.completed` in WAI-State.json
3. **If foundation incomplete: STOP and guide user through setup**
4. Check `_session_state` for recent changes
5. Check boundaries - is this request in scope?

### During Work
- Update `_session_state.last_modified_by` and `last_modified_at`
- Add decisions with impact >= 5 to decisions array
- Signal learnings with impact >= 8 to wheel-signals.jsonl

### Session Continuity Commands
- `'Time'` - Token usage estimate with 80% capacity warnings
- `'Rules'` - List active behavioral guidelines
- `'Closeout'` - Generate updated WAI-State files

---

*This wheel rolls forward with Wheelwright Framework - wheelwright.ai*
