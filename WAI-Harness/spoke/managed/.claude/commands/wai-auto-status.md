# Skill: Auto Status

**ID:** auto-status
**Type:** utility
**Lifecycle:** stable
**Safety Level:** 10
**Advisory:** false

---

## Context

Show Ozi's session-local auto mode status.

If auto mode is on, the output should stay builder-focused:
- ready queue
- work claimed by this session
- recent dispatch activity

It should avoid broad user-interaction prompts because this session is acting as a worker.

## Protocol

1. Read the current session runtime config from `WAI-Spoke/runtime/ozi-sessions/<session-key>.json`.
2. Show:
   - session key
   - auto mode on/off
   - max parallel
   - watch mode on/off
   - poll interval minutes
3. Run `python3 wai_ozi.py` to render the current builder-focused queue view.
4. If the user wants continuous polling, remind them they can run `python3 wai_ozi.py --watch` in the builder session.
5. Optionally show the most recent changelog entries for this session key.

## Related Skills

- `/wai-auto-on`
- `/wai-auto-off`
- `/wai-auto-parallel <n>`
