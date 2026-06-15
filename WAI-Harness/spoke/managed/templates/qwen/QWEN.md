# Qwen Code Integration Instructions for Wheelwright

This project uses Wheelwright (WAI) for session continuity.

## Session Start

On your first turn in a Wheelwright project:

1. Read `AGENTS.md`.
2. Read `WAI-Spoke/WAI-State.json`.
3. Use the first wakeup file that exists:
   - `WAI-Spoke/commands/wai.md`
   - `WAI-Spoke/skills/wai/wai.md`
   - `templates/commands/wai.md`
4. Treat this `QWEN.md` read as already satisfying the wakeup protocol's integration-file step.
5. Do not re-read `QWEN.md` or rescan parent `QWEN.md` files while executing wakeup unless the user explicitly asks.
6. Then respond to the user's message.

## Notes

- Keep this file thin. Behavioral rules belong in the wakeup file and related skills.
- Load additional skill files only when they are relevant to the current task.

## Wakeup Convergence

- Finish the WAI Point briefing before asking for approval on teachings or side actions.
- During wakeup, summarize teachings from filenames/frontmatter only.
- Do not read full teaching bodies during wakeup unless the user explicitly asks to review them now.
