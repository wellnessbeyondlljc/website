# LUG: Wheelwright Artifact Governance

**Version:** 1.0.0  
**Last Updated:** 2026-02-08  
**Status:** Living

---

## Core Directive

**Treat Skills as engines of action. Treat LUGs as repositories of meaning. Treat the filesystem as a governed space, not a canvas.**

---

## Principles

### 1. Skills = Engines of Action
- Must explicitly declare: value generated, artifacts produced, target destinations
- Not documentation dumps
- Every execution ends with reconciliation

### 2. LUGs = Primary Persistence
- LUGs are living, appendable documents
- Hold: design intent, build instructions, decisions, canonical knowledge
- Primary destination for all persistent artifacts
- Evolve over time (not disposable)

### 3. Filesystem = Governed Space
**Sovereign Folders (Only Valid Destinations):**
- `/lug/` - Living unified guides
- `/skills/` - Skill definitions
- `/src/` - Source code
- `/config/` - Configuration
- `/tests/` - Test code

**Forbidden:**
- No ad-hoc markdown in root
- No "notes", "thoughts", "summary", "design" files
- No file creation as substitute for summarization
- No orphan artifacts

---

## Closeout Protocol (Mandatory)

Every work session MUST end with explicit reconciliation:

### 1. Inventory
- What artifacts were produced?
- What insights emerged?
- What decisions were made?

### 2. Classify
**Canonical Knowledge** → Merge into LUG  
**Design Rationale** → Append to LUG  
**Reference Material** → Link in LUG  
**Ephemeral Reasoning** → Discard  
**Redundant Content** → Summarize then discard  

### 3. Reconcile
- Canonical → LUG merge
- Reference → LUG append
- Ephemeral → Delete
- Confirm all moves

### 4. Confirm
- State what was preserved
- State where it was merged
- State what was intentionally discarded
- **No orphan artifacts may remain**

---

## Signal Submission

**When:** At session closeout  
**Where:** WAI-Spoke/WAI-Signals.jsonl  
**What:** Architectural decisions, learnings, patterns, completions

**Signal Schema:**
```json
{
  "timestamp": "2026-02-08T...",
  "session_id": "work-session-id",
  "signal_type": "learning|decision|completion|pattern",
  "impact": 1-10,
  "title": "Short title",
  "description": "Details",
  "category": "CLI|Architecture|Governance|etc",
  "applies_to": "What this applies to"
}
```

---

## File Creation Policy

**File creation is OPT-IN, not default.**

You may ONLY create a file if:
1. ✅ It fits an existing folder policy (`/lug/`, `/src/`, etc.)
2. ✅ It has a declared purpose
3. ✅ It cannot be represented as append/merge into LUG

Otherwise:
- ❌ Summarize
- ❌ Reconcile
- ❌ Discard

---

## LUG Maintenance (CRITICAL)

**LUGs should be LIVE during work:**
- Update as insights emerge
- Append decisions immediately (not at end)
- Auto-save as understanding grows
- Closeout reconciles and confirms

**NOT:**
- ❌ Write ad-hoc markdown
- ❌ Save LUG work only at closeout
- ❌ Create temporary analysis files
- ❌ Leave orphan artifacts

---

## Success Criteria

✅ Root folder remains clean  
✅ No random markdown files appear  
✅ LUGs grow richer over time  
✅ Filesystem stays organized  
✅ Skills end with reconciliation reports  
✅ Every signal explicitly submitted  

---

## Related

- AGENTS.md - Strategic state
- WAI-Signals.jsonl - Signal records
- CLI-Operations.md - Operational LUG
- CLI-v1-Parity.md - Feature LUG
