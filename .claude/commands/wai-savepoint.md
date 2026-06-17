# WAI Savepoint

Save a mid-arc savepoint so you can reset context without losing work state.

---

## Purpose

A savepoint is a **planned mid-arc context reset**. It is NOT a session closeout. The active lug stays `in_progress`, and work resumes in the next session via `/wai` → `[C]ontinue`.

**Use when:** approaching ~80% context with an `in_progress` lug that isn't finished.

---

## Steps

**Step 1: Identify active lug & Capture progress**

Read `WAI-Spoke/lugs/bytype/*/in_progress/*.json`. If multiple in-progress lugs exist, ask the user: "Which lug are you savepointing?"

Compose FOUR plain-English strings:
- work_done: what was DONE this session (backward-looking)
- work_context: what was being WORKED ON — arc context for the resuming agent
- user_next_step: any action the agent told the user to take (omit if none)
- resume_note: what the AGENT does first at next /wai (≤60 chars, agent instruction)

**Step 2: Write `savepoint_note` to the lug file**

Add or update this field in the lug JSON:

```json
"savepoint_note": {
  "done": "<what's been completed>",
  "next_step": "<exact next step>",
  "saved_at": "<ISO timestamp>"
}
```

**Step 3: Write `_savepoint` to `WAI-State.json`**

```json
"_savepoint": {
  "lug_id": "<lug_id>",
  "work_done": "<what was DONE this session>",
  "work_context": "<what was being WORKED ON>",
  "user_next_step": "<any action the agent told the user to take (omit if none)>",
  "resume_note": "<what the AGENT does first at next /wai (≤60 chars, agent instruction)>",
  "saved_at": "<ISO timestamp>",
  "session_id": "<current session_id>",
  "status": "pending"
}
```

`resume_note` is displayed in CONTEXT HEALTH at wakeup. Write it for a human skimming a status line — what to do next, not which lug to open.

**Step 4: Commit**

```bash
git add WAI-Spoke/lugs/bytype/<type>/in_progress/<lug-id>.json
git add WAI-Spoke/WAI-State.json
git commit -m "savepoint: <session_id> — <work_done> | next: <resume_note>"
```

**Step 5: Output exactly**

```
Savepoint saved: "{work_done}". Next: {resume_note}
```

---

## Rules

- Do NOT run `/wai-closeout`
- Do NOT change lug status (stays `in_progress`)
- Do NOT write a session track closeout entry
- The next `/wai` session will detect the pending savepoint in CONTEXT HEALTH and offer `[C]ontinue`
