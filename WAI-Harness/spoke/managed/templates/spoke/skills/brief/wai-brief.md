# WAI Brief — Context Export for External Sessions

**Generate a paste-able context block for an external AI session ("phone a friend").**

Export project context — with or without a topic focus — so any external AI can pick up the conversation with full background, current state, options in play, and open questions.

---

## Execution Context

- **Nodes:** spoke
- **Exposure:** spoke.chat:local
- **Paths Required:** WAI-State.json, lugs/active/WAI-Lugs-active.jsonl, sessions/

---

## Usage

```
/wai-brief                    → full project synopsis
/wai-brief [topic]            → topic-focused briefing
```

Examples:
```
/wai-brief
/wai-brief spoke-id-system
/wai-brief benchmark architecture
/wai-brief Cluster 2 deferral
```

---

## Procedure

### Step 1: Determine Mode

- No argument → **Synopsis mode**
- Argument provided → **Topic mode**

---

### Step 2 (Synopsis Mode): Build Full Project Brief

Read from `WAI-State.json`:
- `_project_foundation.identity` → name, one-liner
- `_session_state.mode`, `wheel.version`
- `_session_state.next_session_recommendation`

Grep `lugs/active/WAI-Lugs-active.jsonl` for:
- Lugs with `status: open | in_progress | ready` (active work)
- Last 3 session-summary lugs (recent history)
- Any lugs with `impact >= 8` from the last 30 days (high-impact decisions)

Read last session `track.jsonl`:
- Extract `decisions[]` across all turns

Output:

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

### Step 3 (Topic Mode): Build Topic-Focused Brief

#### 3a. Gather Topic Evidence

Search for topic across:

1. **Active lugs file** (`lugs/active/WAI-Lugs-active.jsonl`) — grep for topic keywords in `title`, `description`, `tags`, `decisions[]`
   - Collect: lug ID, title, status, relevant decisions, options captured in workflow fields
2. **Current session track** — grep `focus`, `thinking`, `decisions[]`, `open[]` for topic keywords
3. **WAI-State.json** — check `next_session_recommendation` for topic mentions

Rank by relevance: exact ID match > title match > tag match > description match.

Collect up to:
- 5 most relevant lugs
- All track points mentioning the topic
- Any open threads from track `open[]` arrays

#### 3b. Extract Options

From gathered evidence, identify:
- Paths that have been **explicitly considered** (in `thinking`, `workflow`, `decisions`)
- Paths that are **currently open** (in `open[]` arrays)
- Paths that were **rejected** (with reason, if captured)

These become the "Options" section — not invented, only what exists in the record.

#### 3c. Output Topic Brief

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

### Step 4: Delivery

Display the brief in full — formatted, ready to copy.

Then confirm:
```
Brief ready. Copy the block above and paste it into your external session.
Tip: fill in "What I Need From You" before pasting — it shapes the conversation from turn 1.
```

---

## Quality Rules

- **Only surface what exists in the record.** Do not invent options, background, or decisions.
- **Options come from `thinking`, `workflow`, `decisions[]`, and `open[]` fields** — not from general knowledge about the topic.
- **Keep the brief paste-able** — no internal WAI formatting, no JSONL, no lug IDs in the prose (use them as footnotes only if needed for traceability).
- **Topic brief must be self-contained** — the external AI should need nothing else to engage meaningfully.
- **"What I Need From You" is always left blank** — user fills it in. Never pre-fill it.

---

## Related Commands

- `/wai` — Full wakeup briefing (internal use)
- `/wai-status` — Quick health check (internal use)
- `/wai-chat-to-track` — Bring external session results back in
