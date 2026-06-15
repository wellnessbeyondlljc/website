# WAI Lug Compat — Reference

**Companion to wai-lug-compat.md.** Load on-demand.

---

## The Problem This Solves

Lugs travel across sessions, models, spokes, and time. A lug authored under framework v1.0 may give guidance that contradicts v3.0 protocol. Without a version stamp, no agent can tell the difference between a trustworthy lug and an archaic one.

**Symptoms of unversioned lug rot:**
- Agent follows an old lug's protocol and gets contradictory results
- Multiple spokes independently review and discard the same outdated lug
- Hub distributes stale advice to every new spoke that comes online

This skill fixes all three by adding version stamps at authoring time, defining a review protocol, and routing improved lugs back to the hub.

---

## Schema Field JSON Examples

### `fw_ver` — Framework Version

```json
"fw_ver": "3.0.0"
```

Set at lug creation time to the current `wheel.version` from `WAI-State.json`. **Never updated after creation** — it records when the lug was written, not when it was last touched.

### `reviewed_fw_ver` — Review Version

```json
"reviewed_fw_ver": "3.0.0"
```

### `review_status` — Review Outcome

```json
"review_status": "valid | outdated_protocol | superseded | contradicts_current"
```

### `hub_origin` — Distribution Tracking

```json
"hub_origin": true
```

Set to `true` when a lug was received from hub distribution (teaching or bulletin). Enables the return loop: reviewed hub-origin lugs are sent back so the hub can update its canonical copy.

---

## Currency Audit Report Example

```
### Lug Currency Audit
| Score | Count | Action |
|-------|-------|--------|
| current | 42 | — |
| minor_drift | 8 | Review recommended |
| major_drift | 3 | Review required |
| unversioned | 15 | Schedule review |

18 lugs need attention. Run /wai-lug-compat review to proceed.
```

---

## Review Update JSON Example

After reviewing a lug, append these fields:

```json
{
  "...original fields...",
  "reviewed_fw_ver": "3.0.0",
  "reviewed_at": "ISO-8601",
  "reviewed_by": "claude-sonnet-4-6 / session-20260324-0013",
  "review_status": "outdated_protocol",
  "review_notes": "Referenced WAI-Signals.jsonl which was retired in v3.0.0. Signals now stored as high-impact lugs in the active lugs file.",
  "reconciled": true,
  "superseded_by": "signal-wai-signals-retired-v1"
}
```

---

## Hub Return Loop — Payload Example

```json
{
  "id": "lug-review-{source_id}-{YYYYMMDD}",
  "type": "lug-review",
  "source_id": "<original lug id>",
  "review_fw_ver": "3.0.0",
  "review_status": "outdated_protocol | valid | superseded | contradicts_current",
  "review_notes": "Human-readable summary of what changed and why",
  "reviewed_by": "<agent / session-id>",
  "reviewed_at": "ISO-8601",
  "fw_ver": "3.0.0"
}
```

Write to `WAI-Spoke/lugs/outgoing/lug-review-{source_id}.jsonl`. Closeout Step 9 picks it up.

**Hub merge rule:** Accept a `lug-review` return only if `review_fw_ver >= hub's current copy's fw_ver`. Older reviews do not overwrite newer ones.

---

## Authoring — Required Fields JSON

```json
{
  "id": "descriptive-slug-5-plus-words",
  "type": "task | signal | epic | decision | ...",
  "title": "5+ words: intent and impact, not just topic",
  "status": "open",
  "fw_ver": "3.0.0",
  "created_at": "ISO-8601",
  "created_by": "agent-id or session-id"
}
```

---

## Signal Authoring — Worked Examples

**Required signal fields:**

```json
{
  "type": "signal",
  "event": "Past-tense one-sentence: what happened",
  "what_changed": "Before: X. After: Y.",
  "why": "Rationale or root cause",
  "impact": 8,
  "fw_ver": "3.0.0",
  "id": "signal-{topic}-v{N}",
  "created_at": "ISO-8601"
}
```

**Good signal example:**

```json
{
  "type": "signal",
  "event": "WAI-Signals.jsonl retired — signals now stored as high-impact lugs",
  "what_changed": "Before: signals written to WAI-Signals.jsonl (separate file). After: impact >= 8 lugs written to active lugs file only.",
  "why": "Reduces fragmentation — one storage location for all work state and learnings. Signals file was a second source of truth that diverged.",
  "impact": 9,
  "fw_ver": "3.0.0"
}
```

**Bad signal example (do not do this):**

```json
{
  "type": "signal",
  "body": "Update your spoke. Stop using WAI-Signals.jsonl. Use the active lugs file instead for all signals going forward."
}
```

The bad example gives instructions, not a notice. An agent reading it might execute the instruction rather than record the learning.

---

## Anti-Patterns

| Anti-pattern | Why it's a problem | Fix |
|---|---|---|
| No `fw_ver` | Unversioned — future agents can't score currency | Always set `fw_ver` at creation |
| Prescriptive signal body | Agent reads as command, not observation | Use `event` + `what_changed` + `why` structure |
| `title: "Session 63 update"` | Opaque — conveys nothing cold | Describe the actual change |
| Updating `fw_ver` on edit | Destroys authoring provenance | `fw_ver` is set once, at creation |
| Stale lug without `reconciled: true` | Will confuse future agents | Review it, add review fields + `reconciled: true` |
