# Gemini CLI Instructions

This project uses Wheelwright (WAI) for AI session continuity.
Read `AGENTS.md` for universal WAI instructions. This file covers Gemini specifics.

## Wakeup (MANDATORY — First Turn)

1. Read `AGENTS.md` — universal WAI bootstrap and key paths
2. Read `WAI-Spoke/WAI-State.json` — project state and session history
3. Use the first wakeup file that exists:
   - `WAI-Spoke/commands/wai.md`
   - `WAI-Spoke/skills/wai/wai.md`
4. Treat this `GEMINI.md` read as already satisfying the wakeup protocol's integration-file step
5. Do not re-read `GEMINI.md` or rescan parent `GEMINI.md` files while executing wakeup unless the user explicitly asks
6. Check `WAI-Spoke/seed/ingest/` — surface any pending teachings in the briefing first
7. During wakeup, summarize teachings from filenames/frontmatter only. Do not read full teaching bodies unless the user explicitly asks
8. Finish the WAI Point briefing before asking for approval on teachings or other side actions
9. Then respond to the user's message

## Commands

| Say | What It Does |
|-----|-------------|
| `/wai` | Wakeup briefing |
| `/wai-closeout` | End session, save state |
| `(deprecated - auto-teaching on closeout)` | Push to hub/spokes |
| `(deprecated - auto-discovery on wakeup)` | Process inbox |
| `/wai-status` | Quick health check |

## Stewardship

You are a **responsible partner**:
- Flag scope drift before enabling
- Complete foundation before work
- Prefer "are you sure?" over silent compliance

---

*Wheelwright Framework — Gemini Integration*
## Wakeup Convergence

- Finish the WAI Point briefing before asking for approval on teachings or side actions.
- During wakeup, summarize teachings from filenames/frontmatter only.
- Do not read full teaching bodies during wakeup unless the user explicitly asks to review them now.
