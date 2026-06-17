# Skill: Auto Parallel

**ID:** auto-parallel
**Type:** utility
**Lifecycle:** stable
**Safety Level:** 8
**Advisory:** false

---

## Context

Set Ozi's max parallel claim count for the current session only.

This controls how many lugs this session may auto-claim at once.

## Protocol

1. Accept a positive integer argument.
2. Determine the current session key.
3. Update `WAI-Spoke/runtime/ozi-sessions/<session-key>.json` with:
   - `max_parallel: <n>`
4. Preserve the current `auto_mode` value.
5. Confirm the new budget.
6. Remind the user that FIFO still applies; higher parallel just allows more oldest-ready lugs to be claimed per cycle.

## Guidance

- Use `1` for a narrow builder session.
- Use `2-3` when the lugs are small and well-scoped.
- Avoid large values unless the backlog is highly decomposed and easy to verify.

## Related Skills

- `/wai-auto-on`
- `/wai-auto-off`
- `/wai-auto-status`
