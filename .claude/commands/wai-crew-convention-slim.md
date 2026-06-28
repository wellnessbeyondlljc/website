# Crew Convention — Fast Path

> Full protocol: load `wai-crew-convention.md` for full roster, phase division, frontmatter schema, change protocol, CHANGELOG format, authority rules.

**80% case: editing a crew member folder or checking structure.**

---

## Folder Structure

```
crew/
├── SOP.md          # crew-wide standard operating procedure
├── KNOWLEDGE.md    # crew-wide shared vocabulary
├── README.md       # roster index — one row per member
└── {slug}/
    ├── SOP.md          # advisor-specific SOP
    ├── KNOWLEDGE.md    # advisor-specific knowledge
    ├── README.md       # auto-regenerable header + last-20 track entries
    ├── CHANGELOG.md    # Keep-a-Changelog-style history
    └── track.jsonl     # append-only event log
```

Job-title slugs are kebab-case and **never change** after creation.

---

## Frontmatter (required in every {slug}/SOP.md and KNOWLEDGE.md)

```yaml
---
name: Dana
role: delivery-manager
version: 0.1.0
status: active
owner: delivery-manager
permissions: notify
---
```

---

## Version Bump Rules

| Change | Bump |
|--------|------|
| Wording / clarity | patch (0.0.X) |
| New stanza / behavioral addition | minor (0.X.0) |
| Breaks backward compatibility | major (X.0.0) |

**Every version bump requires:**
1. CHANGELOG.md entry (date + what changed)
2. `track.jsonl` event: `{"event": "version_bump", "from": "X", "to": "Y", "ts": "..."}`

---

## Crew Roster (quick lookup)

| Slug | Name | Role |
|------|------|------|
| delivery-manager | Dana | Lead — drives phases, surfaces stalls |
| product-strategist | Pete | Ideation, intent, risk tier |
| architect | Archie | Design, blast radius, rollback |
| ux-designer | Uma | User-facing flows |
| persona-steward | Stella | Personas, copy, paths |
| release-engineer | Will | Build, CI, deploy |
| qa-engineer | Jordy | Verify, evidence |
| security-reviewer | Sage | Authn/z, secrets, PII |
| site-reliability | Reggie | Observability, drift |
| cruft-hygiene | Hank | Dead code, deprecations |
| growth-marketer | Mark | Content + growth |

---

## Adoption Check

```bash
test -f crew/SOP.md && echo PASS
test -f crew/KNOWLEDGE.md && echo PASS
test -f crew/README.md && echo PASS
```
