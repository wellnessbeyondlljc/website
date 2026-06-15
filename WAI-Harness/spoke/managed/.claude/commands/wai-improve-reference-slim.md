# WAI Improve Reference — Fast Path

> Full reference: load `wai-improve-reference.md` for fit report template, terminology examples, full priority matrix, phase adjustment table, JSON lug template, backlog review output template.

**Quick lookup: priority matrix, fit classifications, promotion audit.**

---

## Priority Matrix

| Velocity | Cost | Fit | Priority |
|----------|------|-----|----------|
| High | Low | Aligned | P0 |
| High | Med | Aligned | P1 |
| High | Low | Neutral | P1 |
| Med | Low | Aligned | P1 |
| High | High | Aligned | P2 |
| Med | Med | Aligned | P2 |
| Low | any | any | P4 |
| any | any | Tension | flag |

**Ceiling rules:**
- Foundation incomplete → ceiling P3
- `scope: schema|protocol` → design discussion required before P0/P1

---

## Fit Classifications

| Classification | Meaning |
|----------------|---------|
| `net_new` | No overlap found |
| `extends` | Builds on existing lug/feature |
| `supersedes` | Makes an existing lug obsolete |
| `conflicts` | Contradicts existing decision |
| `duplicate` | Identical to existing lug |

`duplicate` or `conflicts` → stop until user acknowledges.

---

## Similarity Types (Step 2a)

| Type | Meaning |
|------|---------|
| Exact | Same challenge AND hypothesis |
| Challenge overlap | Same problem, different solution |
| Hypothesis overlap | Same solution for different problem |
| Dependency | Must complete other first |
| Conflict | Contradicts other's outcome |

---

## Promotion Audit (Step 6c)

PEV dogfood checklist:
- `perceive` items name specific files (not "check the codebase")
- `execute` steps are single-action with explicit paths
- `verify` items are checkable (true/false, not "looks good")
- No open conflicts in fit check
- All terminology reconciled
