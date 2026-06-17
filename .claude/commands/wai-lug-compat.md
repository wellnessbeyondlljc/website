# WAI Lug Compatibility Advisor

**Version-aware lug lifecycle — identify outdated lugs, review them against the current framework, send improved versions back to the hub.**

> See **wai-lug-compat-reference.md** for worked examples, JSON samples, and anti-patterns.

---

## Execution Context

- **Nodes:** spoke, hub
- **Exposure:** spoke.chat:local
- **Trigger:** `/wai-lug-compat` or automatically at wakeup when stale lug count exceeds threshold

---

## Schema Fields

All new lugs require `fw_ver` (set once at creation from `WAI-State.json → wheel.version`).

| Field | Purpose |
|-------|---------|
| `fw_ver` | Framework version at authoring time. Never updated after creation. |
| `reviewed_fw_ver` | Framework version at review time. |
| `review_status` | `valid`, `outdated_protocol`, `superseded`, or `contradicts_current` |
| `hub_origin` | `true` if received from hub distribution. Enables return loop. |

---

## Currency Scoring

Compare `lug.fw_ver` against current `WAI-State.json → wheel.version`:

| Score | Condition | Action |
|-------|-----------|--------|
| `current` | Same major.minor | Trust — no review needed |
| `minor_drift` | Same major, minor gap <= 2 | Review recommended |
| `major_drift` | Major version differs | Review required before acting |
| `unversioned` | No `fw_ver` field | Treat as suspect — schedule review |

---

## Step 1: Currency Audit

Run on demand or at wakeup when `major_drift + unversioned > 5`.

1. Load all lugs from `WAI-Spoke/lugs/bytype/` (scan active statuses)
2. Read current version from `WAI-State.json → wheel.version`
3. Score each non-reconciled lug by `fw_ver`
4. Report counts by score with recommended actions
5. If no action needed: "All lugs current — no review required."

---

## Step 2: Review Protocol

For each lug in `major_drift` or `unversioned` (or `minor_drift` if requested):

1. Read the lug content fully
2. Identify protocol references, path names, field names, behavioral directives
3. Check each against current framework (`templates/commands/`, `WAI-Spoke/skills/`)
4. Classify using `review_status` values
5. Append review fields: `reviewed_fw_ver`, `reviewed_at`, `reviewed_by`, `review_status`, `review_notes`
6. If substantively outdated: set `reconciled: true`; if replaced, set `superseded_by`

**Review is interpretation, not rewrite.** Do not alter original lug fields. Only append review fields. If a lug needs substantive updating, create a new lug and set `superseded_by`.

---

## Step 3: Hub Return Loop

After reviewing any lug where `hub_origin: true`:

1. Create a `lug-review` payload with: `source_id`, `review_fw_ver`, `review_status`, `review_notes`, `reviewed_by`, `reviewed_at`
2. Write to `WAI-Spoke/lugs/outgoing/lug-review-{source_id}.jsonl`
3. Closeout Step 9 (Outgoing Delivery) routes it to hub
4. Hub accepts only if `review_fw_ver >= hub's current copy's fw_ver`

---

## Step 4: Authoring Guidance

Every new lug requires: `id`, `type`, `title` (5+ words), `status`, `fw_ver`, `created_at`, `created_by`.

Signals are high-impact lugs (`impact >= 8`). They are **notices** — structured observations (`event` + `what_changed` + `why`), not instructions.

---

## Wakeup Integration

At Step 4 (Load Lugs): count lugs by currency score. If `major_drift + unversioned > 5`, surface in briefing. Do **not** block wakeup — currency audit is advisory.

## Closeout Integration

At Step 9 (Outgoing Delivery): include any `lug-review-*.jsonl` files from `WAI-Spoke/lugs/outgoing/` in the hub delivery batch.

---

## Related Skills

- `wai-lug-schema.md` — lug schema, storage, lifecycle
- `wai-closeout.md` — Step 9: Outgoing Delivery
- `wai.md` — Step 4: Load Lugs (currency audit trigger)
