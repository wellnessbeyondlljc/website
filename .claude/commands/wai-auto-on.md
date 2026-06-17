# Skill: Auto On

**ID:** auto-on
**Type:** utility
**Lifecycle:** stable
**Safety Level:** 8
**Advisory:** false

---

## Context

Enable Ozi auto mode for the current session only. This is session-local builder mode, not a shared project-wide switch.

When enabled, Ozi:
- focuses on ready work
- claims eligible lugs for this session
- respects this session's parallel budget
- polls in watch mode every 5 minutes when run with `python3 wai_ozi.py --watch`
- does not force other sessions into auto mode

## Protocol

1. Determine the current session key using Ozi's runtime logic.
2. Write/update `WAI-Spoke/runtime/ozi-sessions/<session-key>.json` with:
   - `auto_mode: true`
   - current `max_parallel` (default 1 if unset)
   - `watch_mode: true`
   - `poll_interval_minutes: 5`
3. Confirm the current session key and active parallel budget.
4. Offer to run `python3 wai_ozi.py` immediately so Ozi can claim ready work now.
5. If the user wants continuous lightweight polling, start `python3 wai_ozi.py --watch` in that builder session.

## Notes

- This setting is local to the current terminal/session key.
- Other sessions on the same project keep their own Ozi mode.
- Use `/wai-auto-parallel <n>` to raise or lower this session's worker budget.
- Use `/wai-auto-off` to return this session to observational mode.
- FIFO claim order is based on oldest `created_at` first among eligible `ready` lugs.

## Related Skills

- `/wai-auto-off`
- `/wai-auto-status`
- `/wai-auto-parallel <n>`
