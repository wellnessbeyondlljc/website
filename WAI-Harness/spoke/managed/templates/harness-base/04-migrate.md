# 04 — Migrate (brownfield): subsume existing data, then re-assert

Run only if `02-detect.md` chose **brownfield**. The strategy is **idempotent full re-assert**: bring every component to its v3.0.0 shape without a per-version diff engine. A spoke 49 teachings behind runs this once and lands current.

## 1. Subsume old data forward (never delete)

| Found | Action |
|---|---|
| Flat or `active/` lugs | Move into `WAI-Spoke/lugs/bytype/{type}/{status}/`. Preserve ids + content. |
| Old bolts/patterns | Move under `WAI-Spoke/bolts/bytype/**` and `patterns/bytype/**`. |
| Prior `seed/ingest/processed/` teaching files | Keep — they record what was already adopted. |
| Pre-base teachings still "pending" | They are **subsumed by this base** — do not adopt them one by one. Move to an `archive/` and note `absorbed_in_base_version: 3.0.0`. |
| Non-standard / unknown files | If unsure whether they hold live data, **write a notation lug** and leave them in place. Do not clobber. |

## 2. Re-assert every base component

Run the same "ensure this state" operations as `03-bootstrap.md` §1–§3. Because they are idempotent, existing-and-correct components are untouched; missing or drifted ones are repaired:

- Ensure all `WAI-Spoke/**` and `.claude/**` directories exist.
- **Install the base payload from this bundle's `payload/`** (self-contained): `payload/tools/verify_engine.py` → `tools/`, `payload/schemas/*.json` → `schemas/`, `payload/commands/*.md` → `.claude/commands/`. These are harness-owned — overwrite. (A spoke on a *newer* lineage keeps its own newer skills; only the v3 base files in the payload are asserted.)

## 3. Add / upgrade the `_harness` ledger

Merge the `_harness` block into the existing `WAI-State.json` (do not drop other fields):

```json
"_harness": { "base_version": "3.0.0", "base_bolt_id": null, "patches_adopted": [], "patches_available": 0, "last_adoption_check": null }
```

If a prior `base_version` existed, just overwrite it with `3.0.0` — the re-assert above already brought the files current.

## 4. Idempotency check

Re-running this file must be a no-op. After a first migrate, a second pass should report "all components current, nothing changed."

→ Continue to `05-hygiene.md`.
