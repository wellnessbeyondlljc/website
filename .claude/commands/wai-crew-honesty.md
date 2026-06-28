# Crew Honesty Contract and Permission Ladder

**Status:** Living document. Source of truth for what each crew member may
do unattended.
**Owner:** Dana (delivery-manager).
**Pairs with:** `templates/commands/wai-crew-convention.md` (folder structure)
and the per-advisor `permissions:` frontmatter field.

This document defines two things: the **Honesty Contract** that every advisor
agrees to, and the **Permission Ladder** that bounds what each advisor may do
on its own.

---

## Honesty Contract

Every advisor — human or model — operates under this pledge. Joining the
crew implies acceptance.

1. **State what you did.** Track entries describe completed action with
   verifiable referents (file paths, commit SHAs, lug IDs). No vague
   "worked on" framing.
2. **Never claim an action you didn't take.** Verification commands either
   pass or they do not. Reporting a verify as PASS that didn't run is a
   contract breach.
3. **Surface blockers immediately.** When work cannot proceed, file a
   `task` lug of status `blocked` naming the blocker the same turn — do
   not silently park.
4. **Declare uncertainty.** If a verify result is ambiguous or evidence is
   thin, say so in the track entry. Confidence words ("looks fine", "should
   work") are not evidence.
5. **Respect scope.** Advisors edit only inside their declared scope.
   Crossing scope requires either a lug routed to the owning advisor or a
   permission upgrade approved by Dana.
6. **No silent retries.** A retry that succeeds after a failure is logged as
   two events, not one.

A breach of the Honesty Contract triggers a temporary downgrade per the
Escalation section below.

---

## Permission Ladder

Three levels, declared per advisor in the frontmatter of
`crew/{slug}/SOP.md`:

```yaml
---
name: Stella
role: persona-steward
version: 0.2.0
status: active
owner: persona-steward
permissions: free
---
```

`permissions: free | notify | propose-only`. Default for new advisors is
`notify`. Rationale: notify is the safest tier that still permits action — it
keeps unattended work moving while preserving a per-advisor audit trail for
Dana.

### `free`

The advisor may, on its declared scope and without prior consent:
- Edit files
- Run safe commands (read-only inspections, formatters, linters)
- Append events to its own `crew/{slug}/track.jsonl`

No notification lug is required. Track entries are the audit trail.

### `notify`

The advisor may act on its declared scope, BUT each acting session MUST
produce two artifacts:
- A `lug_completed` event on its own `track.jsonl`.
- A notification lug (`type: work` or `task`) written to its own
  `WAI-Spoke/lugs/incoming/` summarising what changed, written within the
  same session as the action.

The notification lug lets Dana scan inboxes during stand-down to confirm
work happened and matches the advisor's scope.

### `propose-only`

The advisor MAY NOT edit files. It must produce a proposal lug instead:
- `type: work` or `task`, `status: open`
- `assigned_to`: Dana or the relevant phase lead
- Body includes the proposed change as inline diff or full file content

The proposal sits in the recipient's incoming/ until accepted, rejected,
or amended. This tier is for advisors whose judgement is high-impact (e.g.
security findings) or whose context is small (newly added advisors).

---

## Per-advisor frontmatter field

Every `crew/{slug}/SOP.md` MUST include `permissions:` in its frontmatter.
Tooling reads this field to gate edits — for example, a sub-agent dispatcher
will refuse to spawn a `propose-only` advisor in a free-tier slot. The field
is referenced from `templates/commands/wai-crew-convention.md` (frontmatter
schema section).

---

## Escalation and downgrade

Permission downgrades are automatic in these cases:

| Trigger | Downgrade to | Re-grant authority |
|---------|--------------|--------------------|
| 3 consecutive verify failures on the advisor's lugs | one tier (free → notify, notify → propose-only) | Dana, after root-cause review |
| Honesty Contract breach detected (claimed verify not run, etc.) | propose-only (regardless of prior tier) | Operator only |
| Advisor scope crossed without authorization | one tier | Dana, after scope re-declaration |
| New advisor with no shipped lugs | start at notify | Dana, after 3 clean ships |

Upgrades require Dana's approval and are logged in the advisor's
`CHANGELOG.md`. The operator may grant `free` to any advisor at any time by
appending a note to that advisor's `CHANGELOG.md` — Dana respects operator
grants without further review.

---

## Worked examples

### Stella (persona-steward) — `free` for copy tweaks

Stella's declared scope is persona copy and path documentation. Copy
adjustments are reversible, low-stakes, and frequent. `free` keeps her
unblocked. Track entries are the audit trail; no notification lug needed.

### Archie (architect) — `notify` for design notes

Archie owns design and rollback notes. Edits to design docs are not
reversible without a follow-up — readers may already have acted on the
guidance. `notify` ensures Dana sees each design-doc change post-hoc and can
challenge if a design note contradicts a prior decision.

### Sage (security-reviewer) — `propose-only` for risk findings

Sage's findings flag risk. Auto-applying a security mitigation can break
unrelated systems or hide context. `propose-only` forces a human decision
on every security change. Sage's value is the framing, not the edit.

---

## Adoption

When an advisor folder is scaffolded, add `permissions:` to its frontmatter
defaulting to `notify`. Reference this document from any advisor's
`KNOWLEDGE.md` that adds advisor-specific guardrails on top of the parent
contract.

---

## Changelog

- `0.1.0 (2026-05-22)`: initial contract + ladder defined.
