# WAI Brief — Reference

**Parent skill:** `wai-brief.md`
Load this file on-demand for output templates, search strategy details, and edge cases.

---

## Synopsis Mode Output Template

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WAI PROJECT BRIEF — {name} v{version}
Generated: {ISO date}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## What This Project Is
{one-liner}

## Current Phase
{mode} | Session {session_count}

## Recent High-Impact Decisions
{bullet list from high-impact lugs and last session decisions}

## Active Work
{table: ID | Title | Status}

## What I Need From You
[user fills this in before pasting]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Topic Mode — Evidence Gathering Details

### 3a. Gather Topic Evidence

Search for topic across:

1. **Active lugs** (`bytype/*/open/` and `bytype/*/in_progress/`) — grep for topic keywords in `title`, `description`, `tags`, `decisions[]`
   - Collect: lug ID, title, status, relevant decisions, options captured in workflow fields
2. **Current session track** — grep `focus`, `thinking`, `decisions[]`, `open[]` for topic keywords
3. **WAI-State.json** — check `next_session_recommendation` for topic mentions

Rank by relevance: exact ID match > title match > tag match > description match.

Collect up to:
- 5 most relevant lugs
- All track points mentioning the topic
- Any open threads from track `open[]` arrays

### 3b. Extract Options

From gathered evidence, identify:
- Paths that have been **explicitly considered** (in `thinking`, `workflow`, `decisions`)
- Paths that are **currently open** (in `open[]` arrays)
- Paths that were **rejected** (with reason, if captured)

These become the "Options" section — not invented, only what exists in the record.

---

## Topic Mode Output Template

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WAI TOPIC BRIEF — {topic}
Project: {name} v{version}
Generated: {ISO date}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## Project (30 seconds)
{one-liner}
Framework for AI session continuity — local, hub-spoke, protocol-based.
No cloud dependency. Language: Python + bash + git.

## Topic Background
{1-3 paragraph summary of what the project knows about this topic,
drawn from lug descriptions and track thinking fields}

## Current State
{Where things stand right now — status of relevant lugs, last decision made}

## Options on the Table
{Each option on a separate line, with what's known about it:}

Option A — {description}
  Known: {what we know about this path}
  Risk: {any captured risk or concern}
  Status: {active / considered / rejected — and why if rejected}

Option B — {description}
  ...

## Open Questions
{Unresolved threads from track open[] and lug workflow fields}
- {question 1}
- {question 2}

## What I Need From You
[user fills this in — question, decision needed, or conversation goal]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Usage Examples

```
/wai-brief                        → full project synopsis
/wai-brief spoke-id-system        → topic-focused briefing
/wai-brief benchmark architecture → topic-focused briefing
/wai-brief Cluster 2 deferral     → topic-focused briefing
```

---

## Related Commands

- `/wai` — Full wakeup briefing (internal use)
- `/wai-status` — Quick health check (internal use)
- `/wai-chat-to-track` — Bring external session results back in
