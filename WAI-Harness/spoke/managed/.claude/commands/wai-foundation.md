# WAI Foundation

**Project identity, goals, and boundaries - the project's personality and memory.**

See `wai-foundation-reference.md` for use cases, full JSON schemas, and query examples.

---

## Execution Context

- **Nodes:** spoke, hub
- **Exposure:** spoke.chat:local, spoke.chat:external
- **Paths Required:** spoke_path (current directory)
- **Lug Storage:** `WAI-Spoke/lugs/bytype/foundation/` (completed/, open/)

---

## When to Use

- **First session** - No foundation lugs exist
- **Scope change** - User wants to add/remove from boundaries
- **Goal shift** - Project purpose evolves
- **Constraint change** - New limitations or freedoms
- **Periodic review** - Validate foundation still accurate

## Prerequisites

- WAI-Spoke/ directory exists
- `lugs/bytype/foundation/` directory exists (created at spoke init)

## Follow-ons

- Work can begin once foundation established
- `/wai-closeout` — Captures foundation evolution in session
- `/wai (Step 3a: auto-discovery)` — High-impact foundation changes shared to hub

---

## Teaching Distribution Paths

There are two distinct paths for teachings to reach a spoke. Understanding the distinction is critical to avoid treating local staging as authoritative protocol.

### Hub Teaching Repo (Authoritative)

- **Location:** `hub/teachings_repo/` (distributed by Tender to all spokes)
- **Role:** The **only source of truth** for shared/distributed teaching updates
- **Contents:** Official framework protocol changes, fleet-wide behavioral directives, schema updates
- **Lifecycle:** Authored at the hub, validated, then distributed to spokes via Tender

### Spoke Seed/Ingest (Local Staging)

- **Location:** `WAI-Spoke/seed/ingest/` (session-local staging)
- **Role:** Local staging area for ad-hoc, one-off session loading
- **Contents:** Session-specific teachings, experimental changes, one-time patches
- **Lifecycle:** Loaded per-session, **not authoritative** beyond the current session

### Precedence Rule

**Hub teachings take priority over local ingest files for protocol changes.** When a conflict exists between a hub teaching and a local ingest file, the hub teaching wins. Local ingest is for experimentation and one-off loads, not for overriding distributed protocol.

---

## Foundation Procedure

### 1. Check Existing Foundation

```
Query lugs/bytype/foundation/{open,in_progress,completed}/*.json:
  foundation_lugs = all .json files in bytype/foundation/
  current = foundation_lugs | sort by created_at desc | first
```

If no foundation exists -> **Gather New Foundation**
If foundation exists -> **Verify or Evolve**

### 2. Gather New Foundation (First Time)

Ask conversationally (not a form):

**Identity:**
> "What's the one-sentence description of this project?"
> "Is this code, research, writing, design, or a mix?"
> "What does 'done' look like for you?"

**Boundaries:**
> "What's definitely IN scope for this project?"
> "What should we explicitly AVOID or consider out of scope?"
> "Any constraints I should know about? (time, tech, resources)"

**Approach:**
> "What tools or technologies are we using?"
> "How do you want to work with AI - should I take initiative or check in frequently?"
> "How should decisions get reviewed?"

### 3. Write Foundation Lug

After gathering answers:

1. Generate `id`: `lug-fnd-{random-8-hex}`
2. Set `v: 1`, `type: "foundation"`, `status: "completed"`
3. Populate identity, boundaries, approach from answers
4. Write to `lugs/bytype/foundation/completed/{id}.json`
5. Update `WAI-State.json` cache

**Required fields:** `id`, `ty`, `v`, `title`, `created_at`, `gathered_by`, `identity` (name, purpose, type, done_looks_like), `boundaries` (in_scope, out_scope, constraints), `approach` (tools, ai_style, decision_review). See reference for full schema.

### 4. Verify or Evolve (Returning Session)

Present current foundation summary:

```markdown
**Current Foundation** (v{n}, established {date})

**Identity:** {purpose}
**In Scope:** {list}
**Out of Scope:** {list}
**Constraints:** {list}

Is this still accurate? (yes / needs update)
```

If needs update -> **Evolve Foundation**

### 5. Evolve Foundation

When scope/goals change:

1. Ask: "What's changing and why?"
2. Create evolution lug: `v` = previous + 1, `evolved_from` = previous lug id, `rationale`, `changes` (diff), `full_state` (complete current state). See reference for full schema.
3. Write to `lugs/bytype/foundation/completed/{id}.json`
4. Update `WAI-State.json` cache

---

## WAI-State.json Cache

`_project_foundation` in WAI-State.json caches latest foundation for fast wakeup.

**Rule:** Lugs are source of truth. WAI-State.json is cache for performance. See reference for JSON example.

---

## Impact Threshold

Foundation changes are **always high-impact (impact >= 8)**: initial = 9, expansion = 8, pivot = 10, minor constraint = 8. These automatically become signals for `/wai (Step 3a: auto-discovery)`.

---

## Related Skills

- `/wai-closeout` — Captures foundation evolution in session summary
- `/wai (Step 3a: auto-discovery)` — Shares foundation patterns to hub
- `/wai-status` — Shows current foundation summary

---

*Foundation = The project's personality and memory. Evolves over time, never lost.*
