# WAI IDE Setup

**Agent/IDE Integration Protocol — hooks, settings, and behavioral configuration.**

---

## Execution Context

- **Nodes:** spoke, hub
- **Exposure:** spoke.chat:local
- **Trigger:** First time setup, or when `/wai` detects missing hooks

## When to Use

- Setting up WAI on a new project for the first time
- After cloning a project that uses WAI
- When IDE integration is missing or broken
- When migrating from one AI tool to another

---

## What This Skill Does

WAI needs two hooks to work automatically:

1. **Session start hook** — Runs when a new AI session begins
2. **User prompt hook** — Runs before each user message (first message only triggers wakeup)

These hooks inject a wakeup directive so the agent follows `/wai` without manual invocation. Use UserPromptSubmit if SessionStart is not available. The hook logic handles both cases via the `protocol_completed` flag.

---

## Hook Behavior

Both hooks are **thin triggers** — they inject a directive telling the agent to follow the wakeup protocol:

```
"You are starting a new session. Before responding to the user,
run your WAI wakeup protocol by following the /wai skill in
templates/commands/wai.md. Produce the full WAI Point briefing."
```

**Session detection:** Hooks compare `_session_state.last_session_id` vs `current_session.session_id` in WAI-State.json. If they match (or current is absent), it's a new session.

**One-shot:** Once wakeup runs, the hook sets `protocol_completed = true` and skips subsequent turns.

---

## Claude Code Setup

### Hook Configuration

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "./.claude/hooks/user-prompt-submit.sh"
          }
        ]
      }
    ]
  }
}
```

### Hook Script

Create `.claude/hooks/user-prompt-submit.sh` — a thin trigger that checks WAI-State.json and injects the wakeup directive on first turn only.

See `wai-ide-setup-reference.md` for the full script body, permissions config, and skill command setup.

### Other IDEs

Setup instructions for Gemini, Cursor, and generic AI agents are in `wai-ide-setup-reference.md`.

---

## Setup Verification

After setup, verify:

1. Start a new session
2. Send any message
3. Agent should automatically show WAI Point briefing before responding
4. Briefing shows project name, phase, active work, context health

If briefing doesn't appear:
- Check hook file exists and is executable: `chmod +x .claude/hooks/user-prompt-submit.sh`
- Check settings.json has correct hook path
- Verify WAI-Spoke/WAI-State.json exists
- **CRLF errors?** See troubleshooting in `wai-ide-setup-reference.md`

---

## Entry Point Files

After setup, CLAUDE.md/GEMINI.md become thin pointers — behavioral rules live in skills, not entry files. See `wai-ide-setup-reference.md` for templates.

---

## Related Skills

- `/wai` — Wakeup protocol (what hooks trigger)
- `/wai-closeout` — Sets `last_session_id` at end of session (enables new session detection)
- `/wai-rules` — Project boundaries and guidelines

---

*Setup once. WAI loads automatically every session.*
