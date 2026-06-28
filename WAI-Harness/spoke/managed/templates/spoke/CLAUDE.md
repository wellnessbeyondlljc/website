# Claude Code Instructions

**This project uses Wheelwright (WAI) for AI session continuity.**
Read `AGENTS.md` for universal WAI instructions. This file covers Claude Code specifics.

## Wakeup (MANDATORY — First Turn)

1. Read `AGENTS.md` — universal WAI bootstrap and key paths
2. Read `WAI-Spoke/WAI-State.json` — project state and session history
3. Follow the first wakeup file that exists:
   - `WAI-Spoke/commands/wai.md`
   - `WAI-Spoke/skills/wai/wai.md`
4. Produce the WAI Point briefing before asking for approval on teachings or side actions
5. If teachings are pending, summarize them compactly in the briefing first
6. Do not read full teaching bodies during wakeup unless the user explicitly asks to review them now
7. Then respond to the user's message

The hook at `.claude/hooks/user-prompt-submit.sh` injects this directive automatically on session start.

## Commands

| Command | What It Does |
|---------|-------------|
| `/wai` | Wakeup briefing |
| `/wai-closeout` | End session, save state |
| `/wai-time` | Token usage estimate |
| `/wai-status` | Quick health check |
| `/wai-rules` | Project boundaries |

## Session Tracking

After each turn, append a point to: `WAI-Spoke/session-YYYYMMDD-HHMM/track.jsonl`
See `WAI-Spoke/commands/` for the track-encapsulation schema.

## Complexity Gate

If task affects 2+ files or requires 6+ steps: propose a plan, wait for approval.

## Stewardship

You are a **responsible partner**:
- Flag scope drift before enabling
- Complete foundation before work
- Prefer "are you sure?" over silent compliance

## Tool Ownership (author vs distribute)

Distributed tool/config — everything under `WAI-Harness/spoke/managed/**` (tools, schemas, templates, `.claude/`) plus `MANIFEST.json`, `.mcp.json`, provider files — splits into two roles:
- **Author** the canonical master source at the hub / canonical home (mywheel).
- **Basher owns distribution** — managed→live redeploy, fleet fan-out, re-cut mechanics.

A spoke does NOT edit the distributed source locally — propose changes via a lug (hub to author, Basher to distribute). Apply directly **only when purely local** (`WAI-Harness/spoke/local/**`). When in doubt, route it.

---

*Wheelwright Harness — Claude Code Integration*
