# Strategic Debt Log — deferred design cautions

**Status:** Living protocol.
**Schema:** `WAI-Spoke/reference/caution.schema.json`

This protocol captures intentional speed-over-purity trade-offs in a
structured form so they remain discoverable and actionable instead of
decaying into silent tech debt. Use it whenever a session deliberately
defers an architectural concern to ship something sooner.

---

## When to author a caution

Write a caution **the moment** a speed-vs-completeness decision is made,
in the same session, before moving on. Symptoms that warrant a caution:

- "We'll come back to this after X ships."
- "Good enough for the MVP; refactor in v2."
- "Manual for now; automate later."
- A workaround you would not write if budget were unlimited.

If you can name (a) what you skipped, (b) why skipping was correct now, and
(c) the trigger that should make you revisit — author the caution.

---

## Storage

```
WAI-Spoke/<module>/cautions/caution-<slug>.json
```

One file per caution. `<module>` is the subsystem where the caution lives
(e.g. `realizer`, `wakeup`, `compass`). The slug should be human-readable
and stable.

---

## Required Fields (see schema)

| Field | Notes |
|-------|-------|
| `id` | `caution-<slug>` |
| `created_at` | ISO-8601 UTC |
| `created_during` | `initiative_id`, `epic_id`, `session_id`, or `lug_id` |
| `speed_tradeoff` | What was chosen for speed |
| `risk_deferred` | What architectural question was sidestepped |
| `rationale` | Why the defer was correct in the moment |
| `revisit_trigger` | Observable condition that should cause revisit |
| `revisit_at` | milestone \| phase \| ISO-8601 date \| `on <event>` |
| `status` | `open` \| `resolved` \| `superseded` |

`revisit_at` and `revisit_trigger` are intentionally redundant — `revisit_at`
gives wakeup a date/event it can check programmatically; `revisit_trigger`
gives the human reader the *why*.

---

## Wakeup Integration

At session start, the wakeup protocol scans
`WAI-Spoke/**/cautions/caution-*.json`. For each caution with `status:
"open"`:

1. If `revisit_at` is a date and now >= that date → surface in the brief.
2. If `revisit_at` matches the current phase or a closed milestone → surface.
3. Otherwise → silent.

Surfaced cautions appear under a "REVISIT DUE" section of the wakeup brief
with the caution `id`, `speed_tradeoff`, and `risk_deferred`. The operator
decides whether to act now, re-defer (update `revisit_at`), or close
(`status: resolved` with `resolved_at` + `resolved_by`).

---

## Worked Example

```json
{
  "id": "caution-realizer-no-relationship-graph",
  "created_at": "2026-05-20T15:36:00Z",
  "created_during": "session-111-realizer-v1",
  "speed_tradeoff": "Realizer v1 dispatches lugs by id without a relationship graph between initiatives.",
  "risk_deferred": "Cross-initiative dependency tracking — current dispatcher cannot detect when initiative A blocks initiative B.",
  "rationale": "MVP scope was single-initiative dispatch. Relationship graph would have doubled effort and risked missing the launch window for the proof.",
  "revisit_trigger": "When more than one initiative is active concurrently AND any cross-initiative blocker is observed.",
  "revisit_at": "on second-active-initiative",
  "status": "open",
  "links": {
    "initiative": "realizer-v1",
    "related_feature_lug": "feature-framework-check-later-caution-object-v1"
  }
}
```

---

## Closing a caution

When the trigger fires and the work is actually done:

```json
{
  "status": "resolved",
  "resolved_at": "2026-07-04T00:00:00Z",
  "resolved_by": "impl-relationship-graph-v1"
}
```

If the trigger is no longer meaningful (e.g. the deferred-on system was
removed): mark `superseded` with a note in `links`.

---

## Anti-patterns

- **No caution for a real defer.** Speed decisions without cautions become
  silent debt. The protocol is mandatory for intentional shortcuts.
- **Vague `revisit_trigger`.** "Eventually" or "when there's time" is not a
  trigger. Name the observable condition.
- **Catch-all module path.** Don't dump every caution in `cautions/` at the
  spoke root. Group by the subsystem they actually live in so future readers
  find them while reading that subsystem.
- **Editing a caution in place.** Cautions are append-only in spirit —
  update `status` and add `resolved_*` fields, but don't rewrite history.
