---
name: Crew Parent Knowledge
role: crew
version: 0.1.0
status: active
owner: delivery-manager
---

# Crew KNOWLEDGE — parent

Shared vocabulary and conventions for the entire crew. Inherited by every
`crew/{slug}/KNOWLEDGE.md` (see `templates/commands/wai-crew-convention.md` §
(d)).

## Vocabulary

| Term | Definition |
|------|------------|
| Phase | One of the six work stages — Ideate, Design, Implement, Build, Verify, Observe. |
| Lead | The advisor who owns the gate decision for a phase. One per phase, sometimes a tool (Tender). |
| Consult | An advisor who participates in a phase without owning its gate. |
| No-show | A phase that closes without its lead producing a `track.jsonl` event. |
| Stall | A lug routed to an advisor sitting unacknowledged past the 24h SLA. |
| Stanza | A level-2 markdown heading and its body. Unit of inheritance for SOP/KNOWLEDGE. |
| Permission tier | One of `free | notify | propose-only` — declared in per-advisor frontmatter. |
| Track event | One line of an advisor's `track.jsonl`. Vocabulary defined in lug 683f1af48fc5. |

## Naming conventions

- Folder slugs: kebab-case, role-based, never change after creation.
- Human names: single first name, lives in `name:` frontmatter.
- Files: `SOP.md`, `KNOWLEDGE.md`, `README.md`, `CHANGELOG.md`, `track.jsonl`.
- Versions: semver in `version:` frontmatter; bumps logged in `CHANGELOG.md`.

## Framework integration points

| Touchpoint | What the crew uses it for |
|------------|--------------------------|
| `WAI-Spoke/lugs/incoming/` | Inbound lugs land here for the named advisor to pick up. |
| `WAI-Spoke/lugs/bytype/` | Authored / shipped lugs live here, organized by type and status. |
| `WAI-Spoke/sessions/*/track.jsonl` | Session-level event log; **read-only** for the crew. |
| `crew/{slug}/track.jsonl` | Per-advisor append-only event log; the crew writes here. |
| `WAI-State.json` | Project state — read for context, written only by closeout/wakeup tooling. |
| `templates/commands/wai-crew-convention.md` | Canonical structural spec — source of truth. |

## Inheritance reminder

If a child file omits a stanza present in the parent, the parent stanza is
the effective stanza for that advisor. Child files do not need to repeat
parent content — only override or extend.

To see the effective document for an advisor, mentally merge parent stanzas
with child stanzas, child wins on name collision. There is no grandparent.

## Roster lookup

Roster lives in `crew/README.md` and the canonical convention doc. Both must
be updated when a crew member is added, removed, or renamed.
