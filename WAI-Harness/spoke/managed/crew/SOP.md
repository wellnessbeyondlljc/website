---
name: Crew Parent SOP
role: crew
version: 0.1.0
status: active
owner: delivery-manager
---

# Crew SOP — parent

Living document. Inherited by every `crew/{slug}/SOP.md` stanza-by-stanza
(see `templates/commands/wai-crew-convention.md` § (d) for inheritance rules).

## Phases

Work flows through six phases: **Ideate → Design → Implement → Build → Verify
→ Observe**. Each phase has a lead advisor (gate decision owner) and
optional consults. The phase mapping lives in `templates/commands/wai-crew-convention.md` § (b).

A phase opens when its lead writes a `phase_open` event to their `track.jsonl`.
A phase closes when its lead writes a `phase_close` event with an outcome.

## Lug messages

Work between crew members travels as lugs. A lug routed to an advisor lands
in `WAI-Spoke/lugs/incoming/` for that advisor to pick up at next activation.
Replies are new lugs, not edits to the original.

When an advisor cannot complete the requested work, they reply with a lug of
type `task` and status `blocked`, naming the blocker and proposed unblocking
step.

## Stall handling

Dana (delivery-manager) watches per-advisor track logs. If a lug routed to an
advisor sits unacknowledged for 24 hours, Dana files a `stall` lug naming the
advisor, the blocked work, and the elapsed time. A second 24-hour window
escalates to the operator.

A phase that closes without its lead producing a track entry counts as a
no-show — Dana files a stall lug retroactively.

## Escalation path

Disputes between advisors escalate to Dana. Disputes Dana cannot resolve
(scope conflicts, ownership unclear) escalate to Ozi. Strategic disagreements
go to the operator. There is no fourth level.

## Honesty Contract reference

Every advisor operates under the Honesty Contract and Permission Ladder — see
the per-advisor frontmatter field `permission` (`free | notify | propose-only`).
The contract itself is defined alongside the Permission Ladder spec (Phase A
lug 11b153d55bfc). Until that lug ships, advisors operate at `notify` tier by
default.

## Versioning

Crew members bump their own folder's `version:` per
`templates/commands/wai-crew-convention.md` § (e) and log changes in their own
`CHANGELOG.md`. Parent SOP version bumps are Dana's call; member folders
inherit silently on the next read.

## Boundaries

- Advisors do not edit other advisors' folders directly.
- Advisors do not edit `WAI-Spoke/sessions/*/track.jsonl` (immutable record).
- The parent SOP and parent KNOWLEDGE are the only files Dana edits without
  raising a proposal.
