# Skill: Auto Off

**ID:** auto-off
**Type:** utility
**Lifecycle:** stable
**Safety Level:** 10
**Advisory:** false

---

## Context

Disable Ozi auto mode for the current session only.

Ozi remains available for briefing and queue awareness, but this session stops auto-claiming new work.

## Protocol

> **Runtime base** is the active harness: `WAI-Harness/spoke/local/runtime/` on v4 spokes (legacy v3 spokes only: `WAI-Spoke/runtime/`). Never write the v3 path on a v4 spoke — it resurrects a `WAI-Spoke/` phantom (P12 savepoint-circuit breaker).

1. Determine the current session key.
2. Update `WAI-Harness/spoke/local/runtime/ozi-sessions/<session-key>.json` so `auto_mode: false`.
3. Keep the current `max_parallel` value for later reuse.
4. Confirm that only future auto-claims stop; already claimed work remains in progress until explicitly handed off or completed.

## Related Skills

- `/wai-auto-on`
- `/wai-auto-status`
