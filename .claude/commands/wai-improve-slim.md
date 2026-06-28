# WAI Improve — Fast Path

> Full protocol: load `wai-improve.md` for challenge matching, priority matrix, backlog review mode, promotion protocol, reframe protocol.

**80% case: a user submits an idea and it needs intake → fit check → scoring → lug.**

---

## Execution Flow

```
Step 0: Load spoke context (WAI-State.json foundation)
Step 1: Intake — challenge, hypothesis, origin, scope
Step 2: Similarity and fit check (mandatory before lug creation)
Step 3: Refinement questions (≤3 at a time)
Step 4: Evaluate and score
Step 5: Output as idea lug
```

---

## Step 0 — Load Spoke Context

Read `WAI-Spoke/WAI-State.json`: `one_liner`, `success_looks_like`, `boundaries.*`, `current_phase`.
No foundation lug at all → stop, run `/wai-foundation` first.

---

## Step 1 — Intake

- **Challenge** — what breaks, slows, or is missing?
- **Hypothesis** — "If we [do X], then [outcome Y] because [reason Z]"
- **Scope** — `skill|protocol|schema|tooling|multi|trivial`

Trivial scope → skip Steps 2–4, go directly to Step 5.

---

## Step 2 — Fit Check (Mandatory)

Scan open lugs → classify: Exact / Challenge overlap / Hypothesis overlap / Dependency / Conflict.
Scan `templates/commands/` for existing coverage.
If duplicate or conflict → **stop** until user acknowledges.

Fit report: `net_new | extends | supersedes | conflicts | duplicate`

---

## Step 4 — Scoring

| Dimension | Options |
|-----------|---------|
| Velocity Lift | low / medium / high |
| Implementation Cost | Low (1 session) / Medium (2-3) / High (epic) |
| System Fit | Aligned / Neutral / Tension |
| Generality | All spokes / Hub / Framework / Single |

**Priority:** High velocity + Low cost + Aligned = P0. Low velocity = P4.

---

## Step 5 — Output Lug

Required fields: `spoke_context_loaded: true`, `fit_classification`, `challenge`, `hypothesis`, `challenge_id`, `priority`
Status: `raw` (unprocessed) → `proposed` (fit check done) → `approved` (PEV added)

Missing any required field → status stays `raw`.
