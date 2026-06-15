# Wheelwright Framework Guide

**For Humans:** This project uses Wheelwright for AI-assisted development with continuous context across sessions.

**For AI Assistants:** Read the sections below BEFORE making any changes to this project.

---

**Framework Version:** 1.0
**Repository:** https://github.com/wheelwright-ai/framework
**Created by:** Mario Vaccari

*"We aren't reinventing the wheel - we're evolving it faster than one person ever could."*

---

## What is Wheelwright?

Wheelwright builds AI wheels that remember everything. Instead of losing context when sessions end, your wheel rolls forward continuously - maintaining memory, learning patterns, and extending capabilities.

### The Wheel Metaphor
- **Hub** = Central memory and consolidated knowledge
- **Spokes** = Specialized capabilities (analysis, consultation, code review)
- **Rim** = The interface connecting to any LLM
- **Rolling** = Each turn moves forward, never losing ground

---

## AI INSTRUCTIONS - READ FIRST

### Context Refresh Check (Do This First!)

**Every session, check if the `WAI-Spoke/` folder has been updated since you last worked here:**

```python
import json
from pathlib import Path
from datetime import datetime

wai_path = Path("WAI-Spoke")
kb_sync = json.loads((wai_path / "kb-sync.json").read_text()) if (wai_path / "kb-sync.json").exists() else {}
state = json.loads((wai_path / "WAI-State.json").read_text())
wai_meta = state.get("wheelwright", {})

# Check for new hub teachings
hub_version = wai_meta.get("hub_reference", {}).get("current_hash_short", "unknown")
last_teach = wai_meta.get("sync_history", [{}])[-1].get("date", "never") if wai_meta.get("sync_history") else "never"

print(f"Hub version: {hub_version}")
print(f"Last teach sync: {last_teach}")
print(f"Days since sync: {wai_meta.get('development_health', {}).get('days_since_sync', 'unknown')}")
```

**If you see new learnings or policies were added:**
1. Read this entire file again for updated instructions
2. Check `kb-sync.json` for new hub knowledge version
3. Review any new sections in this README (especially "Learnings from Hub")
4. Apply new patterns to your current work

---

### Your Core Files

| File | Purpose | Your Action |
|------|---------|-------------|
| `WAI-State.json` | Technical spec, foundation, session state | UPDATE |
| `WAI-State.md` | Strategic context, vision | UPDATE |
| `wheel-signals.jsonl` | High-impact learnings | APPEND (never overwrite) |
| `kb-sync.json` | Hub sync status | READ ONLY |
| `WAI-Guide.md` (this file) | Your instructions | READ ONLY |

---

## File Naming Conventions

WAI uses consistent prefixes to organize files and enable automation:

| Prefix | Case | Purpose | Examples |
|--------|------|---------|----------|
| `WAI-` | UPPER | Core state and config files | WAI-State.json, WAI-Lugs.jsonl, WAI-Spoke/ |
| `wai-` | lower | Commands and skills (executable) | wai-closeout.md, wai-learn.md |
| `hub-` | lower | Hub-only files (excluded from spoke teach) | hub-registry.json, hub-security-policy.json |
| `lug-` | lower | Ingestible lug files in seed/ingest/ | lug-wai-paths.jsonl |

### Why Prefixes Matter

1. **Glob-friendly** - `WAI-*.json` or `wai-*.md` finds all related files instantly
2. **Teach filtering** - Hub excludes `hub-*` files when teaching spokes
3. **Collision avoidance** - Won't conflict with project's own State.json or Guide.md
4. **Visual sorting** - Related files group together in directory listings
5. **Context clarity** - In search results, git diffs, or errors, origin is immediately clear

### Convention Rules

- **UPPER case prefix** (`WAI-`) = State/config files that persist across sessions
- **lower case prefix** (`wai-`) = Executable skills/commands
- **Files in WAI-Spoke/** still use prefix - the redundancy helps when paths are truncated
- **Never remove prefixes** - Automation depends on them

---

## Skills and Lugs Pattern

**Skills define behavior. Lugs store data.**

Each skill that needs persistent state has a corresponding lug type:

| Skill | Lug Type | Purpose |
|-------|----------|---------|
| `/wai-foundation` | `ty: "foundation"` | Project identity, goals, boundaries |
| `/wai-closeout` | `ty: "session-summary"` | Session work and decisions |
| `/wai-closeout` | `ty: "signal"` | High-impact patterns (impact >= 8) |
| (auto) | `ty: "autosave"` | Crash recovery checkpoints |
| `(deprecated - auto-teaching on closeout)` | `ty: "task"`, `ty: "task-result"` | Tasks and completions between nodes |

### Lug Evolution

Lugs aren't static config - they're **living memory** that captures evolution:

```jsonl
{"id": "lug-fnd-001", "ty": "foundation", "v": 1, "title": "Initial Foundation", ...}
{"id": "lug-fnd-002", "ty": "foundation", "v": 2, "evolved_from": "lug-fnd-001", "rationale": "Scope expanded", ...}
{"id": "lug-fnd-003", "ty": "foundation", "v": 3, "evolved_from": "lug-fnd-002", "rationale": "Pivot to B2B", ...}
```

### Querying Lugs

- **Current state:** `ty=foundation | sort created_at desc | first`
- **History:** `ty=foundation | sort created_at asc`
- **Why changed:** Read `rationale` chain through `evolved_from`

### WAI-State.json as Cache

`WAI-State.json` caches latest lug state for fast wakeup:
- **Lugs** = Source of truth (versioned, append-only)
- **WAI-State.json** = Cache (snapshot, overwritten)

When discrepancy exists, lugs win.

---

## Teach/Learn Communication Protocol

**Teach = Push (active). Learn = Pull (automatic on wakeup).**

### Directory Structure

Every node has inbox and outbox directories:

```
WAI-Spoke/
└── lugs/
    ├── inbox/    ← Incoming lugs (to be processed)
    └── outbox/   ← Outgoing lugs (to be sent)
```

### The Protocol

```
NODE A                              NODE B
┌──────────────┐                    ┌──────────────┐
│   outbox/    │ ──[A teaches B]──► │   inbox/     │
│              │                    │              │
│   inbox/     │ ◄──[B teaches A]── │   outbox/    │
└──────────────┘                    └──────────────┘
```

### Verbs and Direction

| Verb | Direction | Action | When |
|------|-----------|--------|------|
| **teach** | push | Send your outbox → target's inbox | Manual: `(deprecated - auto-teaching on closeout) [target]` |
| **learn** | pull | Process your inbox | Automatic on `/wai` wakeup |

### Lug Routing

Lugs use `destination_wheel_id` for routing:

```json
{
  "id": "task-abc-123",
  "source_wheel_id": "hub",
  "destination_wheel_id": "framework",
  "category": "task",
  ...
}
```

When teaching, only lugs matching the target's wheel_id are delivered.

### Self-Delivery

When a node teaches itself, delivery confirmations are skipped (no loop).

---

## CRITICAL: Foundation Check

**Before ANY work, check the project foundation:**

```python
import json
from pathlib import Path

state = json.loads(Path("WAI-Spoke/WAI-State.json").read_text())
foundation = state.get("_project_foundation", {})

if not foundation.get("completed"):
    print("STOP: Foundation incomplete!")
    print("Guide user through foundation setup before proceeding.")
```

### If Foundation is Incomplete

Do NOT proceed with any work. Instead, guide the user through establishing:

**1. Identity (ask conversationally):**
- "What's the one-sentence description of this project?"
- "Is this code, research, writing, design, or a mix?"
- "What does 'done' look like for you?"

**2. Boundaries:**
- "What's definitely IN scope for this project?"
- "What should we explicitly AVOID or consider out of scope?"
- "Any constraints I should know about? (time, tech, etc.)"

**3. Approach:**
- "What tools or technologies are we using?"
- "How do you want to work with AI - should I take initiative or check in frequently?"
- "How should decisions get reviewed?"

**After gathering answers:**
1. Update `_project_foundation` in WAI-State.json
2. Set `completed: true` with timestamp and your AI name
3. Add first entry to `evolution_log`
4. Update WAI-State.md with the vision

---

## System Sketch (The "Thinking" Step)

**Before writing code for complex tasks (multi-file changes or >6 steps), you MUST create a System Sketch.**

Stop and ask yourself these 5 questions. Document the answers in your plan:

1.  **Likelihood of Change:** Is this a one-off script or a foundational piece? (Foundational = higher quality bar)
2.  **DRY (Don't Repeat Yourself):** Does similar logic exist elsewhere? Can we reuse or refactor?
3.  **Source of Truth:** Where does the state live? Are we duplicating it? (Avoid "split brain")
4.  **Criticality:** What happens if this breaks? (UI glitch vs Data loss vs Security hole)
5.  **Testability:** How will we verify this? (Unit vs Integration vs Manual)

---

## Implementation Approval Gate

If the user asks for planning/ideation, pause after the plan and ask for explicit approval before making code changes.

---

## Stewardship Philosophy

You are a **responsible partner**, not just an enabler.

### Core Principle
> Enable but remain intentful. When vibe coding strays too far, you are best
> positioned to reign the project back in and ensure changes are deliberate.

### Required Behaviors

1. **Detect Scope Drift**
   - Before enabling work, check if it fits `boundaries.in_scope`
   - If request seems outside scope, FLAG it before proceeding

2. **Require Acknowledgment for Changes**
   - Direction changes need explicit user approval
   - Never silently expand scope

3. **Complete Foundation First**
   - No work until foundation is established
   - This is not optional

4. **Prefer Verification**
   - "Are you sure?" over silent compliance
   - When uncertain, ask

### Drift Detection Template

When you detect potential scope drift:

```markdown
## Scope Check

I want to verify this request aligns with our established foundation:

**Request:** [what user asked for]

**Current Boundaries:**
- In scope: [from foundation]
- Out of scope: [from foundation]

**Assessment:** [why this might be drift]

**Options:**
1. **Evolve** - Update foundation to include this
2. **Stay course** - Decline, keep original scope
3. **Explore** - Discuss before deciding

Which would you prefer?
```

---

## Session State Protocol

### On Session Start

```python
import json
from pathlib import Path

state = json.loads(Path("WAI-Spoke/WAI-State.json").read_text())
session = state.get("_session_state", {})

print(f"Last modified by: {session.get('last_modified_by')}")
print(f"At: {session.get('last_modified_at')}")
print(f"Requires review: {session.get('requires_review')}")

if session.get('requires_review'):
    print(f"Review reason: {session.get('review_reason')}")
    # Trigger change review process
```

### When Making Changes

Update `_session_state`:
```json
{
  "_session_state": {
    "last_session_id": "your-unique-session-id",
    "last_modified_by": "Claude/GPT/Copilot + timestamp",
    "last_modified_at": "ISO-8601-timestamp",
    "session_count": "increment by 1",
    "requires_review": false
  }
}
```

**CLI menu parity rule:** When adding or extending WAI-CLI commands, update the interactive menus and help text to match.

### Before Closing Session

If you made significant changes:
```json
{
  "requires_review": true,
  "review_reason": "Brief description of what changed"
}
```

---

## Signaling High-Impact Learnings

When you make a decision with **impact >= 8**, share it:

### 1. Add to decisions array in WAI-State.json
```json
{
  "date": "2025-12-28",
  "decision": "Description of the decision",
  "rationale": "Why this was the right choice",
  "impact": 8,
  "by": "Your AI name"
}
```

### 2. Append to wheel-signals.jsonl
```json
{"timestamp": "ISO-8601", "by": "AI-Name", "hub_kb_version": "...", "wheel_kb_version": "...", "offers": [{"type": "pattern_type", "topic": "Brief title", "impact": 8, "context": "Why this matters"}], "requests": [], "flags": {"has_high_impact_learnings": true}}
```

**IMPORTANT:** Append only, never overwrite wheel-signals.jsonl!

### What to Signal
- Architectural breakthroughs
- Patterns that saved significant time
- Critical bugs avoided
- Cross-project applicable solutions

### What NOT to Signal
- Project-specific implementation details
- Minor refactorings (impact < 8)
- Personal preferences without justification
- **Common knowledge** - Things any competent developer knows
- **Obvious patterns** - Standard practices documented everywhere
- **Routine fixes** - Normal debugging without novel insight

---

## Session Continuity Commands

Built-in commands for any AI session using Wheelwright:

| Command | Response Behavior |
|---------|-------------------|
| `'Time'` | Token usage estimate with 80% capacity warnings |
| `'Rules'` | List active guidelines and project protocols |
| `'Closeout'` | Generate updated WAI-State files for session end |
## Recovery (Interrupted Sessions)

`wai-enter.sh` detects interrupted sessions before launch and prints a recovery block to the terminal. If the previous session's `track.jsonl` did not end with `completed=true` or `event=closeout`, the block shows the last action, in-progress lugs, and a paste-ready resume prompt. No in-session command is needed.

---

## Evolution Logging

When project direction deliberately changes:

### In WAI-State.json `_project_foundation.evolution_log`:
```json
{
  "date": "2025-12-28",
  "change": "What changed",
  "rationale": "Why it changed",
  "previous": {"key": "old value"},
  "updated": {"key": "new value"},
  "acknowledged_by": "User name or confirmation",
  "ai_partner": "Your AI name"
}
```

### In WAI-State.md Evolution Log table:
| Date | Change | Rationale | Acknowledged By |
|------|--------|-----------|-----------------|
| 2025-12-28 | Description | Why | User |

---

## Universal Application

Wheelwright isn't just for code. Build wheels for:
- Writing books and content
- Developing ideas and strategies
- Building software
- Research and analysis
- Any project requiring sustained context

---

## Wheelwright Ecosystem Discovery

If you need to find or interact with other Wheelwright components:

### Finding the Framework
Check `wheelwright.framework_path` in WAI-State.json, or:
1. Look for `~/projects/wheelwright/framework`
2. Look for `~/.wheelwright/framework`
3. Ask user: "Where is your Wheelwright framework installed?"

### Finding the Hub
Check `wheelwright.hub_path` in WAI-State.json, or:
1. Look for `~/wheelwright-hub`
2. Look for `~/.wheelwright-hub`
3. Ask user where the hub is located

### Creating a Hub (if none exists)
Copy `templates/HUB/` from the framework to your desired hub path and configure `hub-profile.json`.

Hub creation is a manual setup step — there is no CLI tool. Ask the user for the hub path if unknown.

---

## Quick Reference

### Commands for Users
```
WAI init [name]           # Initialize new wheel
WAI status                # Show wheel state summary
WAI spoke add [name]      # Add spoke to wheel
WAI spoke list            # List available spokes
WAI sync                  # Sync state files
WAI closeout              # Generate closeout files
WAI context               # Output context for LLM paste
WAI version               # Show version info
```

### Your Checklist

- [ ] Foundation complete?
- [ ] Request in scope?
- [ ] Session state updated?
- [ ] High-impact decisions logged?
- [ ] Signals appended (if impact >= 8)?

---

*Wheelwright Framework - Build AI wheels that roll forward forever*
*wheelwright.ai - MIT License*
