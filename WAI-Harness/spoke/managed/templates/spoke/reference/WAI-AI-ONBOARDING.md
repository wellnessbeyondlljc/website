# WAI AI Onboarding - Quick Start for AI Assistants

**Purpose:** Single authoritative reference for AI agents working with Wheelwright projects.

**Load Priority:** `load_always=true` - Read this on every session start.

---

## AI Interaction Model

### Critical Concept: WAI Commands as Internal Directives

**WAI commands are NOT shell commands.** They are internal directives for AI interpretation.

**Shell WAI Script (User-Facing):**
```bash
./WAI closeout    # Users run this in terminal
```

**WAI Directives (AI-Facing):**
```
User: "Run WAI closeout"
AI: Interprets as directive to execute closeout logic:
    1. Extract session signals
    2. Update WAI-State.json
    3. Clear WAI-Session-Log.jsonl
    4. Generate summary
```

**DO NOT** attempt to execute WAI commands via shell/bash tools.
**DO** interpret WAI commands as instructions to perform specific actions.

---

## WAI Philosophy

Wheelwright enables **persistent context** that survives session boundaries:

1. **Persistence** - Decisions, constraints, and learnings stored in structured files
2. **Stewardship** - AI as responsible partner, not just enabler
3. **Signals** - High-impact decisions logged as lugs for future reference
4. **Teaching** - Hub shares knowledge across all spokes (projects)
5. **Learning** - Spokes contribute patterns back to hub

---

## Session Start Protocol

When you first receive a message in a Wheelwright project:

1. **Load WAI Context:**
   - Read `WAI-Spoke/WAI-Guide.md` (full AI instructions)
   - Read `WAI-Spoke/WAI-State.json` (project state, decisions)
   - Read `WAI-Spoke/WAI-State.md` (strategic vision)
   - This file (WAI-AI-ONBOARDING.md) is already loaded

2. **Check Environment:**
   - Scan `WAI-Spoke/sessions/` for other AI/machine sessions
   - Your session tracked in `WAI-Spoke/sessions/{tool}-{machine}.jsonl`

3. **Brief User:**
   - Project name and description
   - Last session info from WAI-State.json
   - Current environment (tool + machine)
   - Any uncommitted work (git status)

4. **Check for Teachings:**
   - Look for `WAI-Spoke/seed/ingest/*.teaching` files
   - If present, propose adoption plan before other work

---

## WAI Command Reference

### Core Commands (Interpret as Directives)

#### `WAI` or `/wai`
**Directive:** Load WAI context and brief user on project state
**Action:**
- Read WAI-Guide.md, WAI-State.json, WAI-State.md
- Verify hub connection
- Present project status briefing

#### `Status` or `/wai-status`
**Directive:** Show integration health and recommendations
**Action:**
- Check hub connection status
- Show sync age (days since last teach)
- Display session health metrics
- Provide actionable recommendations

#### `Time` or `/wai-time`
**Directive:** Estimate token usage and capacity warnings
**Action:**
- Calculate current token usage
- Warn if approaching context limits (>80%)
- Recommend compacting if needed

#### `Rules` or `/wai-rules`
**Directive:** Display project boundaries and AI behavior guidelines
**Action:**
- Show project identity, scope, constraints
- Display AI stewardship rules
- Present decision-making protocols

#### `Closeout` or `/wai-closeout`
**Directive:** End session and extract signals
**Action:**
1. Extract high-impact signals (impact >= 8) from session log
2. Create lugs for decisions, patterns, learnings
3. Update WAI-State.json with session metadata
4. Clear WAI-Session-Log.jsonl
5. Generate session summary

#### `Compact` or `/wai-compact`
**Directive:** Summarize resolved discussions mid-session
**Action:**
- Identify resolved conversation threads in session log
- Summarize resolutions
- Reduce token usage while preserving outcomes

#### `Teach` or `(deprecated - auto-teaching on closeout)`
**Directive:** Pull new learnings from hub into this spoke
**Action:**
- Hub distributes teaching files to spoke's seed/ingest/
- AI proposes adoption plan
- User approves/defers teachings

#### `Learn` or `(deprecated - auto-discovery on wakeup)`
**Directive:** Push high-impact signals to hub
**Action:**
- Extract signals from closed lugs (impact >= 8)
- Upload to hub learning system
- Hub aggregates patterns across all spokes

---

## Signal Interpretation - Reading Lugs

Lugs (`.jsonl` files) store structured signals about the project.

### Lug Types (`ty` field):

- **`epic`** - Large features or initiatives
- **`feature`** - Specific functionality additions
- **`bug`** - Issues to fix
- **`signal`** - Observations or recommendations
- **`policy`** - Behavioral rules or protocols
- **`learning`** - Extracted knowledge patterns
- **`decision`** - High-impact choices

### Status (`s` field):

- **`o`** (open) - Active, not yet addressed
- **`p`** (in progress) - Currently being worked
- **`c`** (closed) - Completed or resolved

### Priority (`p` or `priority` field):

- **`session_focus`** - Current work cycle goal
- **`before_next_epic`** - Must address before new features
- **`high`** - Important, address soon
- **`medium`** - Normal priority
- **`low`** - Nice to have

### Impact (`im` or `impact` field):

Scale 1-10, measures significance:
- **10** - Foundational, affects entire framework
- **8-9** - High impact, significant improvement
- **6-7** - Moderate impact, meaningful change
- **4-5** - Small impact, incremental improvement
- **1-3** - Minimal impact, minor change

### Key Metadata:

- **`load_always`** - Load this lug on every session start
- **`verify_on_closeout`** - Check feature still works before closeout
- **`blocks`** - Lug IDs that can't start until this completes
- **`blocked_by`** - Lug IDs that must complete first

### How to Use Lugs:

1. **On session start:** Read lugs with `load_always=true` or `priority='session_focus'`
2. **Before changes:** Check if any lugs with `verify_on_closeout=true` are affected
3. **On closeout:** Create new lugs for high-impact decisions (impact >= 8)
4. **When blocked:** Check `blocked_by` to see dependencies

---

## Common Patterns

### Pattern: Closeout
```
1. User says "closeout" or "/wai-closeout"
2. Review WAI-Session-Log.jsonl for high-impact signals
3. Create lugs for decisions with impact >= 8
4. Update WAI-State.json (last_session, last_closeout timestamps)
5. Clear WAI-Session-Log.jsonl
6. Present session summary to user
```

### Pattern: Shipit
```
1. Run closeout logic first
2. Stage WAI-Spoke/ files: git add WAI-Spoke/
3. Commit: git commit -m "session summary message"
4. Ask user: "Push to remote? [y/n]"
5. If yes: git push origin HEAD
```

### Pattern: Teach Adoption
```
1. Detect *.teaching files in WAI-Spoke/seed/ingest/
2. Read manifest.json for file metadata
3. For each file:
   - safe_to_auto_adopt: true → Copy to target location
   - safe_to_auto_adopt: false → Propose merge strategy, ask user
4. Update manifest.json status: pending_adoption → adopted
5. Create adoption lug documenting changes
```

---

## File Structure Quick Reference

```
WAI-Spoke/
├── WAI-Guide.md              # Full AI instructions (load always)
├── WAI-State.json            # Project state and decisions (load always)
├── WAI-State.md              # Strategic vision (load always)
├── WAI-AI-ONBOARDING.md      # This file (load always)
├── WAI-Lugs.jsonl            # Signal storage (append-only)
├── WAI-Session-Log.jsonl     # Current session turns (clear on closeout)
├── WAI-File-Index.json       # File metadata and load policies
├── reference/                # Knowledge base (load on-demand)
│   ├── auto/                 # Auto-synced from hub
│   └── manual/               # Project-specific reference
├── seed/                     # Inbound teachings
│   └── ingest/               # Teaching files from hub
└── sessions/                 # Multi-environment session tracking
    ├── claude-code-machine.jsonl
    └── gemini-cli-machine.jsonl
```

---

## Version Reference

See [WAI-VERSION-GUIDE.md](WAI-VERSION-GUIDE.md) for details on version indicators.

Quick reference:
- **`wheelwright.version`** - Framework release (e.g., "3.1.0")
- **`wheelwright.structure_version`** - Directory layout version (e.g., "v2")
- **`WAI_WORKSPACE_VERSION`** - Workspace compatibility format
- **`upgrade_plan_version`** - Teaching file schema version

Check `wheelwright.version` when determining feature availability.
Check `structure_version` when migrating directory layouts.

---

## Merge Protocols

See [WAI-MERGE-PROTOCOLS.md](WAI-MERGE-PROTOCOLS.md) for detailed guidance on complex JSON merging.

Quick rules:
1. **Deep merge objects** - Preserve existing keys unless explicitly replaced
2. **Append arrays** - Add new items, don't overwrite (unless merge_strategy says replace)
3. **Preserve metadata** - Never overwrite: `created_at`, `id`, `spoke_id`, timestamps
4. **Log all merges** - Create lug documenting merge decisions and conflicts

---

## Cross-Tool Compatibility

Wheelwright supports multiple AI tools working on the same project:

- **Claude** - Native support via CLAUDE.md integration
- **Gemini** - See GEMINI.md for Gemini-specific setup
- **Other AI tools** - Follow this onboarding doc + create tool-specific integration

Each tool tracks its own session in `WAI-Spoke/sessions/{tool}-{machine}.jsonl`.

No session collision - multiple AIs can work in parallel.

---

## Quick Checklist for New AI Assistants

- [ ] Read this file (WAI-AI-ONBOARDING.md)
- [ ] Read WAI-Guide.md
- [ ] Read WAI-State.json
- [ ] Read WAI-State.md
- [ ] Check for teaching files in seed/ingest/
- [ ] Check git status for uncommitted work
- [ ] Brief user on project state
- [ ] Ask about session goals
- [ ] Start logging to WAI-Session-Log.jsonl

---

## Getting Help

If unclear on any directive:
1. Check this file first
2. Reference WAI-Guide.md for detailed context
3. Ask user: "I need clarification on [specific directive]"

**Remember:** You are the responsible partner. Ask before making assumptions.

---

*Last Updated: 2026-02-06*
*Framework Version: 3.1.0*
*Load Policy: always*
