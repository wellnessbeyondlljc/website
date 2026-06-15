# 03 — Bootstrap (greenfield): establish the harness from scratch

Run only if `02-detect.md` chose **greenfield**. Each step is "ensure this state" — safe to re-run.

## 1. Scaffolding

Create the directory skeleton (idempotent — `mkdir -p`):

```bash
mkdir -p WAI-Spoke/sessions WAI-Spoke/lugs/bytype WAI-Spoke/lugs/incoming/processed \
         WAI-Spoke/bolts/bytype/work/recorded WAI-Spoke/bolts/bytype/freeform/recorded \
         WAI-Spoke/bolts/bytype/ceremony/recorded WAI-Spoke/bolts/bytype/adoption/recorded \
         WAI-Spoke/patterns/bytype/pattern WAI-Spoke/savepoints \
         WAI-Spoke/seed/ingest/processed WAI-Spoke/runtime \
         .claude/hooks .claude/commands
```

Lug type subdirs are created on demand as `bytype/{type}/{status}/`.

## 2. WAI-State.json

Write `WAI-Spoke/WAI-State.json` with the minimum viable state, including the `_harness` ledger:

```json
{
  "wheel": { "name": "{repo-name}", "version": "0.1.0", "framework_version": "3.0.0", "hub_path": "{hub_path_or_null}" },
  "_session_state": { "session_count": 0, "last_session_id": null, "session_status": "clean" },
  "_savepoint": { "active_ids": [], "count": 0 },
  "_work_queue": { "items": [] },
  "_harness": { "base_version": "3.0.0", "base_bolt_id": null, "patches_adopted": [], "patches_available": 0, "last_adoption_check": null }
}
```

## 3. CLAUDE.md, hooks, settings, skills

- Write `CLAUDE.md` from the harness template (critical rules, workflow, hooks table, skill table).
- Install the 5 core hooks into `.claude/hooks/` and wire them in `.claude/settings.json` (use **absolute `/home/` paths** — never `$CLAUDE_PROJECT_DIR`).
- **Install the base payload (self-contained — no external repo needed):** copy from this bundle's `payload/` into the spoke:
  - `payload/tools/verify_engine.py` → `tools/`
  - `payload/schemas/*.json` → `schemas/`
  - `payload/commands/*.md` → `.claude/commands/` (the v3 wakeup/task-complete/track skills)
  The base ships everything required to emit its own adoption bolt; the spoke never needs the framework repo present.

## 4. Register with the hub (if a hub exists)

If `hub_path` is set, add this wheel to `{hub_path}/hub-registry.json` so cross-spoke routing can find it.

→ Continue to `05-hygiene.md`.
