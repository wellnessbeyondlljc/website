# Crew Convention — canonical folder layout, inheritance, and versioning
> Fast path: load `wai-crew-convention-slim.md` first. Load this file only when deep protocol is needed.

**Status:** Living document. Source of truth for all `crew/` work.
**Owner:** Dana (delivery-manager).

This document defines how the `crew/` folder is structured, how member folders
inherit from the parent, how versions are bumped, and how change history is
captured. Any change to a `crew/` member folder must conform to this spec.

---

## (a) Folder Hierarchy

```
crew/
├── SOP.md          # crew-wide standard operating procedure (parent SOP)
├── KNOWLEDGE.md    # crew-wide shared vocabulary and conventions
├── README.md       # roster index — one row per crew member
└── {slug}/         # one folder per advisor, using the job-title slug
    ├── SOP.md          # advisor-specific SOP (overrides parent by stanza name)
    ├── KNOWLEDGE.md    # advisor-specific knowledge (overrides parent by stanza name)
    ├── README.md       # auto-regenerable header + last-20 track entries hoisted
    ├── CHANGELOG.md    # Keep-a-Changelog-style history
    └── track.jsonl     # append-only per-advisor event log
```

Job-title slugs are kebab-case and stable: they never change after creation.
Human names live in the frontmatter of each `{slug}/SOP.md` (`name:` field) so
roster lookups can map either direction.

---

## (b) Roster

The crew has 11 members. Dana spans every phase as the driver; Archie is
architecture-only. Personas marked *Lead* in the phase table own that phase's
gate decisions; *Consults* members participate but do not gate.

| Folder slug         | Human name | Role                                                             |
|---------------------|------------|------------------------------------------------------------------|
| delivery-manager    | Dana       | Lead — drives phases, detects no-shows, surfaces stalls via lug  |
| product-strategist  | Pete       | Ideation, intent, risk tier                                      |
| architect           | Archie     | Design, blast radius, rollback                                   |
| ux-designer         | Uma        | User-facing flows, screens                                       |
| persona-steward     | Stella     | Personas, copy, paths                                            |
| release-engineer    | Will       | Build, CI, deploy                                                |
| qa-engineer         | Jordy      | Verify, evidence, regression                                     |
| security-reviewer   | Sage       | Authn/z, secrets, deps, PII                                      |
| site-reliability    | Reggie     | Observability, drift                                             |
| cruft-hygiene       | Hank       | Dead code, deprecations                                          |
| growth-marketer     | Mark       | Content + growth (Clara merged in)                               |

### Phase division of labor

| Phase     | Lead                     | Consults           |
|-----------|--------------------------|--------------------|
| Ideate    | Pete                     | Stella             |
| Design    | Archie                   | Uma, Sage          |
| Implement | (Tender sub-agents)      | Hank               |
| Build     | Will                     | —                  |
| Verify    | Jordy                    | Stella, Sage       |
| Observe   | Reggie                   | Hank               |

---

## (c) Frontmatter Schema

Every `{slug}/SOP.md` and `{slug}/KNOWLEDGE.md` MUST begin with YAML
frontmatter:

```yaml
---
name: Dana                  # human name
role: delivery-manager      # folder slug — must match the parent directory
version: 0.1.0              # semver — see (e) for bump rules
status: active              # active | draft | retired
owner: delivery-manager     # slug of the advisor who owns this file (usually self)
permissions: notify         # free | notify | propose-only — see wai-crew-honesty.md
---
```

The `permissions:` field is required. Semantics, defaults, and escalation
rules are defined in `templates/commands/wai-crew-honesty.md` — read that
file before assigning a new advisor a tier.

The `track.jsonl` event vocabulary and the last-20 README hoist convention
are defined in `templates/commands/wai-crew-track-schema.md`. Phase SOPs
live under `crew/phases/{phase}.md` — one stub per phase.

`crew/SOP.md` and `crew/KNOWLEDGE.md` use the same frontmatter shape but with
`role: crew` and `owner: delivery-manager` (Dana owns the parents).

---

## (d) Inheritance Rules

Child documents (`crew/{slug}/SOP.md`, `crew/{slug}/KNOWLEDGE.md`) inherit from
their parent (`crew/SOP.md`, `crew/KNOWLEDGE.md`) by **stanza name**.

A stanza is a level-2 heading (`## Stanza Name`) and everything beneath it up
to the next level-2 heading.

**Resolution rules:**
1. Walk the parent document; for each `## Stanza Name`, check if the child has
   the same `## Stanza Name`.
2. If the child has it: child wins (full override of that stanza body).
3. If the child does not have it: inherit silently (parent stanza is the
   effective stanza for that advisor).
4. Stanzas present only in the child are additive (no parent counterpart).
5. Inheritance is one level only — there is no grandparent.

Removing or renaming a parent stanza is a **major** version bump (see (e))
because every child relying on it is silently affected.

---

## (e) Semver Bump Rules

`version:` in frontmatter follows semver-like rules:

| Change                                                        | Bump  |
|---------------------------------------------------------------|-------|
| Wording / clarification / typo fix                            | patch |
| New stanza added (no behavioral change to existing ones)      | minor |
| Existing stanza removed or renamed                            | major |
| Existing stanza meaning materially changed                    | major |
| Frontmatter field added                                       | minor |
| Frontmatter field renamed or removed                          | major |
| Status flip (active → retired)                                | major |

Every version bump MUST add a row to the file's owning `CHANGELOG.md`.

---

## (f) CHANGELOG.md Format

Each `crew/{slug}/CHANGELOG.md` follows
[Keep-a-Changelog](https://keepachangelog.com/) style:

```markdown
# Changelog — {Human Name} ({slug})

All notable changes to this advisor's SOP, KNOWLEDGE, or contract.

## [Unreleased]

## [0.2.0] — 2026-06-01
### Added
- New stanza "Escalation Path" in SOP.md.

## [0.1.0] — 2026-05-22
### Added
- Initial SOP.md and KNOWLEDGE.md scaffolded.
```

Sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
The unreleased section accumulates changes until a version is cut.

---

## (g) Authority and Ownership

- **Dana (`delivery-manager`)** owns `crew/SOP.md` and `crew/README.md`. She
  is the only crew member who edits the parent SOP without raising a proposal.
- **Each advisor owns their own folder.** Other advisors propose changes via
  a lug routed to that advisor's folder, never by direct edit.
- **Cross-cutting changes** (e.g. a new mandatory frontmatter field) require
  a parent SOP update by Dana; child folders adopt within one version cycle.
- **No-show detection:** if a phase passes without the lead advisor producing
  a track entry, Dana files a stall lug. See `crew/SOP.md` § Stall Handling.

---

## Adoption Verification

```bash
test -f crew/SOP.md && echo PASS
test -f crew/KNOWLEDGE.md && echo PASS
test -f crew/README.md && echo PASS
grep -c '^| .* | .* | ' crew/README.md | awk '$1>=11{print "PASS"}'
```
