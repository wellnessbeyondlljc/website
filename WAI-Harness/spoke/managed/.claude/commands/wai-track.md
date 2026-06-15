# WAI Track v1.0.2

Session governance protocol — per-turn JSONL ledger, behavioral overlays, and export format.

**Spec source:** `WAI-Spoke/reference/wai-track-v1.0.2.yaml`  
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

**When:** After completing the response — before the next user turn.  
**How:** Write the entry to `WAI-Spoke/runtime/track-buffer.json` as a single JSON object (not JSONL).  
**Skip condition:** Plan mode only — tool calls are blocked. Resume normal appends when plan mode exits.

### Schema

```json
{
  "event": "turn",
  "turn": 9,
  "source": "model",
  "ts": "2026-05-29T12:12:00Z",
  "phase": "orient",
  "focus": "what this turn was about",
  "user_msg": "exact text of the user's message this turn",
  "user_intent": "synthesized intent — what the user was trying to accomplish",
  "action": "what the agent did",
  "outcome": "what changed or was produced (files written, decision reached, error resolved)",
  "thinking": "3-8 sentences explaining the reasoning process, constraints observed, and tradeoffs considered",
  "activity": ["Read wai-track.md", "Edit user-prompt-submit.sh"],
  "files_in": ["files read this turn"],
  "files_out": ["files written or modified this turn"],
  "decisions": ["targeted buffer write over direct append for reliability"],
  "insights": ["v0.34.1 hook text labeled fields Optional, causing them to be skipped"],
  "pivotal_statements": ["user utterances that caused a direction change — quoted verbatim"],
  "fossils": ["dead ends, rejected paths, failed attempts — what was tried and abandoned"],
  "open": ["verify Stop hook fires on buffer-only turns"],
  "closed": ["item from a prior open list that was resolved or delivered this turn"],
  "spokes_referenced": ["track-prompt-lab", "hub"],
  "evolution": "understood the staging pattern already existed in the Stop hook",
  "notes": "optional free-text observations about this turn",
  "gold": "optional: a keeper insight worth propagating to future sessions"
}
```

**Field guidance:**
- `source` — required. Always `"model"` for model-authored entries. The Stop hook uses this to distinguish rich entries from synthesized ones (`"transcript-synth"`).
- `user_msg` — required. Copy the user's exact message verbatim. This is the primary input record for the turn.
- `user_intent` — required. Synthesized: what the user was trying to accomplish (may differ from literal message).
- `action` — required. What the agent did this turn (concrete and specific).
- `outcome` — required. What changed or was produced as a result.
- `thinking` — required. 3–8 sentences. Explain why, not what. Include uncertainty, tradeoffs, what was rejected.
- `activity` — list every tool call made this turn (Read, Edit, Bash, Agent, etc.)
- `files_in` — files read/consumed this turn
- `files_out` — files written or modified this turn
- `decisions` — concrete choices made and their rationale (not just actions taken)
- `insights` — non-obvious observations, pattern recognitions, corrections to prior understanding
- `pivotal_statements` — user utterances quoted verbatim that caused a direction change or reframe
- `fossils` — dead ends, rejected approaches, failed attempts; preserves SI4 decision archaeology
- `open` — unresolved commitments, pending deliverables, detected risks not yet addressed; these persist until explicitly closed
- `closed` — items from a prior turn's `open` list that were resolved or delivered this turn. **This is how the track becomes a self-auditable todo ledger.** Post-compaction recovery: scan all `open` items; subtract any that appear in a later `closed` array. What remains is still owed.
- `spokes_referenced` — **always include the home spoke** (e.g. `["track-prompt-lab"]`) plus any other spokes discussed this turn. Never empty. Enables cross-spoke turn identification in track exports.
- `evolution` — how understanding changed from the start of this turn (leave empty string if nothing changed)
- `notes` — optional free-text; any observations not captured elsewhere
- `gold` — optional; a distilled keeper insight worth surfacing to future sessions

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
{ "event": "closeout", "turn": 18, "ts": "...", "completed": true }
```

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
