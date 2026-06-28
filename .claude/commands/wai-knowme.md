# WAI KnowMe — Spoke Self-Portrait

Generate `WAI-Spoke/KnowMe.md`: a cold-LLM-ready self-portrait of this spoke, written for a collaborating agent that has **no repo access and no session history**. One ~400-line file that bootstraps a fresh agent without traversing WAI-State, scanning lugs, or replaying tracks.

## When to run

- At closeout (optional final step), or each Gardener lifecycle pass.
- On demand: `/wai-knowme`.

The generation act is also a **drift check**: if KnowMe.md cannot be written cleanly (missing state, broken lugs), the spoke has drift that needs resolution — surface it.

## Data sources (read-only)

- `WAI-Spoke/WAI-State.json` — identity, version, `_harness`, foundation, work queue.
- `WAI-Spoke/lugs/bytype/*/open/` + `*/in_progress/` — active work.
- 3 most recent `WAI-Spoke/sessions/*/` summaries — recent trajectory.
- Context health (compaction state, last session status).

## Required sections (in order)

1. **Identity** — name, one-line purpose, stack, WAI phase, hub path.
2. **Current stage** — version, `_harness.base_version` + `fw_ver`, active initiative/epic.
3. **Architecture** — key modules/dirs and what they do (3–8 bullets).
4. **Active work** — top open/in-progress lugs by ROI (id · title · effort · model_fit).
5. **Constraints & rules** — project-specific boundaries (from CLAUDE.md + foundation).
6. **Context health** — clean/interrupted, last session, any drift flags.
7. **How to help** — the 2–3 things a fresh agent should do first here.

## Steps

1. Read the data sources above.
2. Synthesize a narrative (not a data dump) into the 7 sections.
3. Write `WAI-Spoke/KnowMe.md` (overwrite previous).
4. Append a track event: `{ "event": "knowme_generated", "ts": "...", "lines": N }`.
5. If any source was unreadable or empty, note it in the output AND report the drift to the user.

## Output contract

- Self-contained: assume the reader has ONLY this file.
- ~400 lines max — synthesized, current, no stale history.
