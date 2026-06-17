# WAI Brief — Context Export for External Sessions

**Generate a paste-able context block for an external AI session ("phone a friend").**

Reference: `wai-brief-reference.md` — output templates, search strategy details, examples.

## Fuzzy Triggers

Invoke this skill whenever the user's message matches any of these patterns (exact wording not required):

- "phone a friend"
- "get a second opinion" / "seek a second opinion" / "want another opinion"
- "take this to another AI" / "paste this into [ChatGPT / Gemini / another session]"
- "generate a brief for an external session"
- "need context I can share" / "context block" / "paste-able summary"
- "explain the situation to [someone / another model]"
- "help me explain what we're working on"

---

## Execution Context

- **Nodes:** spoke
- **Exposure:** spoke.chat:local
- **Paths Required:** WAI-State.json, bytype/, sessions/

---

## Usage

```
/wai-brief                → full project synopsis
/wai-brief [topic]        → topic-focused briefing
```

---

## Procedure

### Step 1: Determine Mode

- No argument → **Synopsis mode** (Step 2)
- Argument provided → **Topic mode** (Step 3)

### Step 2 (Synopsis Mode): Build Full Project Brief

Read from `WAI-State.json`: identity, mode, version, next_session_recommendation.
Scan `bytype/*/open/` and `bytype/*/in_progress/` for active lugs.
Scan last 3 session-summary lugs and any lugs with `impact >= 8` from the last 30 days.
Read last session `track.jsonl` for `decisions[]`.

Output using the **Synopsis template** from reference file.

### Step 3 (Topic Mode): Build Topic-Focused Brief

Search active lugs, current session track, and WAI-State.json for topic keywords.
Extract options from `thinking`, `workflow`, `decisions[]`, `open[]` — never invent options.
See reference file for full evidence-gathering procedure (3a, 3b).

Output using the **Topic template** from reference file.

### Step 4: Delivery

Display the brief in full — formatted, ready to copy. Then:
```
Brief ready. Copy the block above and paste it into your external session.
Tip: fill in "What I Need From You" before pasting — it shapes the conversation from turn 1.
```

---

## Quality Rules

- **Only surface what exists in the record.** Do not invent options, background, or decisions.
- **Options come from `thinking`, `workflow`, `decisions[]`, and `open[]` fields** — not general knowledge.
- **Keep the brief paste-able** — no internal WAI formatting, no JSONL, no lug IDs in prose.
- **Topic brief must be self-contained** — external AI needs nothing else to engage.
- **"What I Need From You" is always left blank** — user fills it in.
