# Skill Examples Quick Reference

All 16 skills with common use cases and examples.

## Core Navigation Skills

### /wai (Wakeup)
**When:** Starting session, need status overview
**Example:**
User: What am I working on?
AI: (Loads WAI context, briefs user on project state, last session, uncommitted changes)

### /wai-status (Status)
**When:** Health check after 10+ turns or unsure about sync
**Example:**
User: Status
AI: Hub connected: yes, Last sync: 2 hours ago, Sessions active: 1 (this machine)

### /wai-time (Time)
**When:** Concerned about context usage, approaching limits
**Example:**
User: How full is context?
AI: Context usage: 62%, Approaching 70% threshold. Consider closeout soon.

### /wai-rules (Rules)
**When:** Need scope boundaries, want to confirm guidelines
**Example:**
User: What is in scope?
AI: (Shows project boundaries, AI collaboration style, behavioral guidelines)

## Session Lifecycle

### /wai-closeout (Closeout)
**When:** Session ending, need to save progress and update state
**Example:**
User: Done for today
AI: (Extracts signals, logs high-impact decisions, updates WAI-State.json, clears session log)

## Hub Synchronization

### /wai (Step 9b: auto-teach on closeout) (Teach)
**When:** Hub updated, want to pull new learnings/skills
**Example:**
User: Teach
AI: Hub has 3 new skill updates. Import? (yes/no)

### /wai (Step 3a: auto-discovery) (Learn)
**When:** Made high-impact decision (impact >= 8), want to push to hub
**Example:**
User: /wai (Step 3a: auto-discovery)
AI: Found 2 high-impact signals from session. Push to hub? (yes/no)

## Advisory Skills (Auto-Triggered)

### Complexity Advisor
**Triggers:** Task affects 2+ files OR requires 6+ steps
**Example:**
User: Refactor authentication module (touches 5 files)
AI: Complex task detected. Planning required before implementation. Propose a plan? (yes/no)

### Stewardship Advisor
**Triggers:** Work strays from project boundaries
**Example:**
User: Can we add browser extension support?
AI: Out of scope (handled by wheelwright-ai/extension-browser repo). Did you mean: [alternative]?

### Context Advisor
**Triggers:** Context > 60%, session > 20 turns
**Example:**
AI (proactive): Context at 65%. Consider closeout soon to maintain efficiency.

### Foundation Advisor
**Triggers:** Project foundation incomplete
**Example:**
AI: Project foundation incomplete. Need to define: identity, boundaries, approach before substantive work.

### Signal Advisor
**Triggers:** Decision with impact >= 8
**Example:**
(Auto-logs) Decision: Switch from YOLO to ADAPTIVE mode. Impact: 10. Logged to active lugs file as signal lug

### Lug Advisor
**Triggers:** User mentions lugs, task graph, or asks for task management
**Example:**
User: How do I track this task?
AI: Use lugs (task graph). Create with: /wai-lug create [task-name]

---

## Common Workflows

### Start Session
1. Run /wai (get briefing)
2. Run git status (check for uncommitted changes)
3. Define daily goal

### Make Decision (Impact >= 8)
1. Make decision
2. Signal Advisor auto-logs to active lugs file (signal lug, impact >= 8)
3. At closeout, decision flows to hub via /wai (Step 3a: auto-discovery)

### End Session
1. Run /wai-closeout (extract signals, update state, commit)

### Resume After Crash
1. Check terminal — wai-enter.sh prints recovery prompt pre-launch
2. Paste the recovery prompt to Claude to resume
3. Run /wai (get reoriented)

### Sync with Hub
1. Run /wai (Step 9b: auto-teach on closeout) (pull new learnings/skills)
2. Do work
3. Run /wai (Step 3a: auto-discovery) (push signals back)

---

**Last Updated:** 2026-02-08
