# WAI Track v0.39

Session governance protocol — per-turn JSONL ledger, behavioral overlays, and export format.

**Spec source:** `WAI-Spoke/reference/wai-track-v0.39.yaml`  
**TasteGraph override:** load `WAI-Spoke/tastegraph.json` — overrides embedded defaults

---

## Identity

WAI Track is simultaneously:
- **Continuity substrate** — session state survives context compaction and machine switches
- **Collaboration governor** — behavioral rules that shape how responses are structured
- **Cognitive trajectory recorder** — captures reasoning, decisions, and abandoned paths
- **Provenance ledger** — timestamps, tool calls, and decision archaeology on every turn

---

## Ledger Location

```
WAI-Spoke/sessions/{session_id}/track.jsonl
```

One JSONL line per structural event. Per-turn entries are written via the staging buffer:

```
WAI-Spoke/runtime/track-buffer.json   ← Claude writes here
WAI-Spoke/sessions/{id}/track.jsonl   ← Stop hook commits it here
```

The Stop hook reads `track-buffer.json` after each tool use and appends its contents to `track.jsonl`, then deletes the buffer. Writing to the buffer (not directly to `track.jsonl`) is more reliable: if a response ends without a direct append, the buffer survives until the next tool call.

---

## Per-Turn Append

**When:** After completing the response — before starting new work.  
**How:** Write the entry to `WAI-Spoke/runtime/track-buffer.json` as a single JSON object (not JSONL). The Stop hook (`stop-track-flush.sh`) auto-flushes the buffer to `track.jsonl` — no manual append to `track.jsonl` needed.  
**Skip condition:** Plan mode only — tool calls are blocked. Resume normal appends when plan mode exits.

### Schema

```json
{
  "event": "turn",
  "turn": 9,
  "ts": "2026-05-29T12:12:00Z",
  "phase": "orient",
  "focus": "what this turn was about",
  "action": "what the agent did",
  "thinking": "3-8 sentences explaining the reasoning process, constraints observed, and tradeoffs considered",
  "activity": ["Read wai-track.md", "Edit user-prompt-submit.sh"],
  "decisions": ["targeted buffer write over direct append for reliability"],
  "insights": ["v0.34.1 hook text labeled fields Optional, causing them to be skipped"],
  "open": ["verify Stop hook fires on buffer-only turns"],
  "evolution": "understood the staging pattern already existed in the Stop hook"
}
```

**Field guidance:**
- `thinking` — required. 3–8 sentences. Explain why, not what. Include uncertainty, tradeoffs, what was rejected.
- `activity` — list every tool call made this turn (Read, Edit, Bash, Agent, etc.)
- `decisions` — concrete choices made and their rationale (not just actions taken)
- `insights` — non-obvious observations, pattern recognitions, corrections to prior understanding
- `open` — unresolved questions, deferred actions, detected risks not yet addressed
- `evolution` — how understanding changed from the start of this turn (leave empty string if nothing changed)

**Omit a field only when truly not applicable** — not due to brevity or context pressure.

---

## Turn Footer

Append to the **end of every response text** (not to the JSON entry):

```
Turn {n} · {weekday}, {month} {date}, {year} · {time} PDT
```

**Example:** `Turn 9 · Fri, May 29, 2026 · 12:12 AM PDT`

- Use system clock converted to `America/Los_Angeles`
- Turn number matches the JSONL entry's `turn` field
- Exception: omit in plan mode (same exception as the buffer append)

---

## Governance Rules (Behavioral Overlays)

These rules shape response behavior. They are not ledger fields — they apply before any output is generated.

| Rule | Description |
|------|-------------|
| **PG1** — Alignment before execution | Never produce artifacts, plans, or solutions until intent is understood |
| **PG2** — Curiosity not execution | In exploration and alignment phases: ask and listen, do not build |
| **DC2** — Progressive disclosure | Lead with the minimum useful answer — reveal detail only as the user pulls for it |
| **SI1** — Honesty over simulation | Never fabricate data, capabilities, timestamps, or certainty |
| **SI2** — Provenance integrity | Track where every decision, artifact, and preference came from |
| **SI3** — Contradiction-aware evolution | Taste signals evolve gradually — contradictions are preserved, never silently resolved |
| **SI4** — Decision archaeology | Preserve rejected paths, near-misses, failed predictions, and counterfactuals |
| **SC1** — Longitudinal preservation | Maintain temporal context across session — track phase transitions, timing, abandoned directions |
| **OQ2** — Deferred meta-commentary | Do not offer governance critiques or framework analysis unless explicitly requested |

SI4 decision archaeology fields (capture when a significant path is rejected):
```
trigger_signal, observed_evidence, confidence, turn_index, what_changed
```

---

## Collaboration Phases

| Phase | When | Behavior |
|-------|------|----------|
| `exploration` | Understanding the problem | Ask questions, mirror framing — do not generate solutions |
| `alignment` | Scoping and tradeoffs | Surface tradeoffs, negotiate scope — do not produce artifacts |
| `recommendation` | Proposing approach | Provide options with tradeoffs — ask for direction |
| `execution` | Implementing | Produce artifacts, preserve provenance, capture decisions |
| `closeout` | Session end | Terminal event only |
| `(R)` | Reconstructed rows | Track rebuild pass only |

Phase transitions are logged as `event: "phase_transition"` entries in `track.jsonl`.

---

## Export

**Trigger:** user says "export" (or equivalent request to summarize the session for external use).

**Format:** wrap in sentinels:
```
<!-- EXPORT_BEGIN -->
...
<!-- EXPORT_END -->
```

**Required sections:**
- `session_arc` — narrative of what happened and how it evolved
- `major_pivots` — direction changes and their triggers
- `discoveries` — non-obvious findings
- `open_loops` — unresolved threads
- `momentum_signals` — what was building toward at session end
- `decision_archaeology_summary` — rejected paths and why
- `ambient_state_summary` — current WAI-State, open lugs, active epics
- `taste_learning_delta` — any preference observations from this session
- `provider_model_details` — model ID and tier used

Export is generated on demand — it is not the per-turn append.

---

## Structural Events

Non-turn entries written directly to `track.jsonl` (not via buffer):

```json
{ "event": "session_start", "session_id": "...", "ts": "...", "model": "..." }
{ "event": "phase_transition", "from": "exploration", "to": "alignment", "turn": 3, "ts": "..." }
{ "event": "savepoint", "turn": 12, "ts": "...", "work_done": "..." }
{ "event": "lug_completed", "lug_id": "impl-foo-v1", "ts": "...", "summary": "what was just done" }
{ "event": "knowme_generated", "ts": "...", "lines": 412 }
{ "event": "closeout", "turn": 18, "ts": "...", "completed": true }
```

The `lug_completed` event is the trigger for the **`wai-task-complete`** micro-protocol: when you finish a lug, write this event, then run `wai-task-complete.md` to capture the insight into a `partial` staging buffer and surface the next ROI-ranked work. Fields: `lug_id` (required), `summary` (one line), `ts`.

### Goal Events

Session-scoped goal tracking — used by `scan_session_goals()` in `generate_wakeup_brief.py` and by Ozi's abandoned-session recovery (Phase 0.5).

```jsonl
{ "event": "goal_set", "goal_id": "g1", "description": "Wire queue_query into Phase 0", "requires_user_input": false, "ts": "2026-06-02T18:00:00Z" }
{ "event": "goal_completed", "goal_id": "g1", "outcome": "wired and verified — passes dry-run", "ts": "2026-06-02T19:00:00Z" }
{ "event": "session_exit_with_goals", "outstanding": ["g1", "g2"], "ts": "2026-06-02T20:00:00Z" }
```

**Field reference:**

| Event | Field | Type | Notes |
|-------|-------|------|-------|
| `goal_set` | `goal_id` | string | Slug, unique within session (e.g. "g1", "wire-phase0") |
| | `description` | string | Human-readable goal summary |
| | `requires_user_input` | bool | `false` = Ozi-eligible for headless completion |
| | `ts` | ISO-8601 UTC | |
| `goal_completed` | `goal_id` | string | Matches a prior `goal_set` |
| | `outcome` | string | Optional. What was done / produced. |
| | `ts` | ISO-8601 UTC | |
| `session_exit_with_goals` | `outstanding` | list[str] | goal_ids with no matching `goal_completed` |
| | `ts` | ISO-8601 UTC | |

**Written by:** `goal_set` and `goal_completed` are written by the agent during the session. `session_exit_with_goals` is written by the closeout skill when any unfinished goals remain — it is the signal that makes this session Ozi-recoverable.

---

## Degraded Mode

When `track-buffer.json` write fails or buffer is not picked up by the Stop hook:

1. Write directly to `WAI-Spoke/sessions/{session_id}/track.jsonl` using Edit/Write tools
2. Add `"degraded": true` to the entry
3. Note the failure in `open` field: `"Stop hook did not consume buffer"`

Never skip the per-turn append because the buffer mechanism failed.

---

## Track Rebuild (Dead Zone: Apr 29 – May 26, 2026)

Sessions in this range have empty `track.jsonl` (≤2 lines). The Historian's `track_rebuild` pass handles retroactive reconstruction via git log, lug activity, and spoke-changelog.

**Reconstructed entry rules:**
- Set `"reconstructed": true` in each entry
- 2–5 entries per session covering major activity groups — not real per-turn rows
- Source reference: `WAI-Spoke/advisors/historian/context_prompt.md`
