# PathGraph — Spec: Aspiration Inference, Drift Detection, Ephemeral PRD

**Version:** 1.1.0
**Created:** 2026-05-25
**Updated:** 2026-05-30
**Lug:** lug-pathgraph-advisor-spec-v1
**Depends on:** wilbur/docs/spoke-vision/ (archaeology baseline for Minder seed)

---

## Scope

PathGraph is **per-spoke infrastructure** — every spoke has its own PathGraph instance that tracks that spoke's aspiration-to-reality gap. It is not a Wilbur-specific feature; Wilbur happens to be the spoke that also runs a **Fleet Synthesis Layer** on top of its own PathGraph.

```
Hub
└─ PathGraph base schema + extraction protocol (this spec)

Each Spoke (framework, minder, basher, wilbur, ...)
└─ PathGraph instance — spoke-local aspiration index, drift tracker, spirit store

Wilbur (additionally)
└─ Fleet Synthesis Layer — reads all spoke PathGraphs, applies team priority weights,
   produces cross-spoke recommendations and Mario-facing surfaces
```

When this spec describes "modules" (e.g. `minder-core`, `minder-web`), those are sub-components of a specific spoke's PathGraph. The spoke-level field (`spoke_id`) identifies which spoke the aspiration belongs to.

---

## Purpose

PathGraph is the spoke's authoritative record of work — past, present, and future. **The lugs are the PathGraph.** PathGraph is not a separate data store; it is a structured, time-horizon-aware lens over the lug corpus that answers "what is, was, and will be true of this spoke?"

Because PathGraph is built from lugs (which are repeatedly validated by corpus tests, quality gates, and agent execution), it is the most accurate source available for generating design docs, specifications, documentation, changelogs, and vision statements. Other sources (CLAUDE.md, README, session notes) are derived or supplementary — PathGraph is primary.

**Four time horizons:**

| Horizon | Source | Examples |
|---------|--------|---------|
| **History** | Completed lugs, closed epics, version tags | What was built, when, why, how it was verified |
| **Current** | Open + in-progress lugs | Active work, known gaps, in-flight decisions |
| **Near future** | Initiatives (`index.json`), open epics | Roadmap, initiative sequence, focus-lock items |
| **Vision** | Aspirations extracted from session tracks, open-ended goals | Distant intent, stated but unscoped |

PathGraph is the single input to any generated artifact. When an agent produces a design doc, spec, or changelog, it reads PathGraph — not CLAUDE.md, not README, not memory files.

Aspiration extraction from session tracks (described later in this spec) feeds the **Vision layer** of PathGraph. It is one input among four. The other three layers are built directly from the lug corpus.

---

## Core Concepts

### Aspiration

A stated goal or intent extracted from a session track event. An aspiration has:

- `source_session` — which session stated it
- `text` — the stated intent (verbatim or paraphrased)
- `spoke_id` — which spoke this aspiration targets (e.g. `minder`, `framework`, `wilbur`)
- `module` — sub-component within that spoke (e.g. `minder-core`, `minder-web`); null if spoke-level
- `confidence` — `explicit` | `inferred` | `contextual` based on phrasing certainty
- `status` — `open` | `fulfilled` | `drifted` | `abandoned`

Aspirations stated in conversation are treated as commitments to the future, not casual remarks. The Historian has a strong, persistent impulse to manifest what Mario has said.

### Drift

When the intended state (from aspirations) diverges from the current state (from codebase/lugs). Drift is:

- Detected by cross-referencing aspirations against current lug statuses and spoke-vision gap lists
- Classified: `minor` (small gap), `significant` (large gap), `critical` (blocking progress)

Drift accumulates silently when no system tracks it. PathGraph makes drift visible.

### Spirit

The extracted mood, implied constraints, tradeoffs made, core intent, and aspirations from a session track or lug's originating conversation. Each spirit extraction is tagged with confidence:

- `explicit` — Mario stated it directly ("this should work X way")
- `inferred` — conclusion drawn from pattern of decisions
- `contextual` — implied by adjacent context and tradeoffs

### Ephemeral PRD

A lightweight, session-scoped product requirements doc generated fresh at each session start. Contains:

- Vision statement (from aspiration)
- Current state (from code/lugs)
- Proposed design
- Acceptance criteria
- Tangential areas affected

Ephemeral because it exists to drive one specific action — once adopted into a lug, the PRD is archived. Regenerated next session from latest track data.

---

## Multi-File Structure

PathGraph is a directory of files within each spoke's `WAI-Spoke/pathgraph/`:

```
WAI-Spoke/pathgraph/
  index.json          — meta: file list, last rebuild, version, spoke_id
  history.jsonl       — completed lugs + closed epics (append-only)
  current.json        — open + in-progress lugs (rebuilt on change)
  near-future.json    — initiatives, open epics, roadmap sequencing
  vision.jsonl        — extracted aspirations from session tracks (append-only)
  generated/          — artifacts produced FROM pathgraph (never edited manually)
    design-doc.md
    spec-{module}.md
    changelog.md
```

**Rules:**
- `history.jsonl` and `vision.jsonl` are append-only — no records are deleted, only updated (fulfilled, superseded)
- `current.json` and `near-future.json` are rebuilt from the lug corpus on each PathGraph refresh
- `generated/` artifacts are always derived output — they are never the source of truth; PathGraph is
- PathGraph refresh runs: post-session (incremental), nightly (full rebuild), on lug close (targeted)

---

## Generation Interface

PathGraph is the input to all generated artifacts for a spoke. The generation interface:

```python
def generate(artifact_type: str, module: str = None, horizon: str = "all") -> str:
    """
    artifact_type: "design-doc" | "spec" | "changelog" | "vision-statement" | "gap-analysis"
    module:        spoke sub-component to scope to (None = full spoke)
    horizon:       "history" | "current" | "near-future" | "vision" | "all"

    Returns the generated artifact as a markdown string.
    Writes to WAI-Spoke/pathgraph/generated/{artifact_type}.md if called with save=True.
    """
```

**Design principles for generation:**
- Facts come from lug fields (title, perceive, acceptance_criteria, outcome, completed_at)
- Ordering comes from initiative weights + ROI scores (PathGraph is already prioritized)
- Vision content comes from aspiration extraction (vision.jsonl)
- No inference beyond what the lugs say — generation is assembly, not invention
- Each generated artifact cites its source lugs by ID

---

## Lugs as PathGraph Nodes

Every lug type maps to a PathGraph time horizon:

| Lug type | Horizon | Fields used |
|----------|---------|-------------|
| `implementation`, `feature`, `fix` (completed) | History | title, outcome, completed_at, acceptance_criteria |
| `epic` (completed) | History | title, outcome, child_lugs, completed_at |
| `implementation`, `feature`, `task` (open/in-progress) | Current | title, perceive, execute, verify, roi, effort_score |
| `epic` (open) | Current | title, acceptance_criteria, phase, blocked_by |
| `epic` (open, initiative-linked) | Near-future | title, initiative_id, phase |
| `spec` (open) | Current + Near-future | title, what, why, acceptance_criteria |
| Extracted aspirations | Vision | text, spoke_id, module, confidence, status |

The `spoke_id` field on aspiration records links vision-layer entries back to their originating spoke. Cross-spoke aspirations (ones that span multiple spokes) are tagged with all relevant spoke IDs.

---

## Aspiration Record Schema

Full schema: `wilbur/schemas/pathgraph-index.schema.json`

PathGraph vision-layer stores aspiration records. Each record:

```json
{
  "id": "aspiration-{slug}-{hex8}",
  "source_session": "session-20260525-1442",
  "extracted_at": "2026-05-25T00:00:00Z",
  "module": "minder-core",
  "text": "The wakeup brief should fit in under 12k tokens",
  "confidence": "explicit",
  "status": "open",
  "drift_level": null,
  "fulfilled_session": null,
  "tags": []
}
```

PathGraph also stores derived indexes:

- `track_events` — indexed track events with spirit extraction
- `lug_origins` — which session originated each lug
- `decisions` — explicit decisions extracted from tracks
- `stated_aspirations` — primary aspiration records
- `deferred_items` — items deferred in session but not lug'd
- `optimization_opportunities` — patterns identified across sessions

Storage: file-based JSON index. Queryable without a database. Rebuilt incrementally on new session data.

---

## Extraction Protocol

Three-step process for extracting aspirations from session tracks:

**Step 1 — Scan**

Read `track.jsonl` files. Look for events where:

- `focus` contains goal language ("should", "need to", "will", "plan to", "goal", "want")
- `action` describes intended future work
- `open` array contains unresolved items
- `insights` describe structural problems to address
- `mood` contains frustration or aspiration signals

**Step 2 — Parse**

For each candidate event, extract the aspiration text and classify:

- **Module**: match to `minder-core` / `minder-web` / `minder-telegram` / `minder-forge` / `minder-fleet` / `minder-ideas` / `minder-tracks` / `framework` / `hub` / `basher` / `cross-module`
- **Confidence**:
  - `explicit` — Mario stated it directly
  - `inferred` — implied by pattern of decisions or repeated behavior
  - `contextual` — suggested by adjacent tradeoffs or constraints

Also extract for each track event:

- `mood` — tone and emotional signal of the session
- `implied_constraints` — constraints that shaped decisions
- `tradeoffs_made` — what was sacrificed for what
- `core_intent` — the underlying goal beneath the surface action

**Step 3 — Deduplicate**

Check existing index for near-duplicate aspirations (same module + similar text). Options:

- **Merge** — if two aspirations are equivalent, keep the most recent and mark the older as superseded
- **Supersede** — if a later aspiration replaces an earlier one (restated with different scope)
- **Strengthen** — if a new mention reinforces an existing aspiration, increase its weight/recency

Do not create duplicate records. Near-duplicate detection uses module + text similarity.

---

## Drift Detection Protocol

Run after extraction. For each open aspiration:

1. Check if a completed lug exists that fulfills it — if yes, mark `status = fulfilled`, record `fulfilled_session`
2. Check spoke-vision gap lists (`wilbur/docs/spoke-vision/`) for the module — if the aspiration maps to a documented gap, confirm drift
3. If no fulfillment found and gap confirmed → `status = drifted`, `drift_level = significant`
4. If aspiration was stated more than 30 sessions ago with no progress → `status = abandoned` (flag for review, do not auto-abandon without human confirmation)

Drift classification rules:

| drift_level | Condition |
|-------------|-----------|
| `minor` | Aspiration partially addressed; small gap remains |
| `significant` | Aspiration stated clearly; no meaningful progress |
| `critical` | Aspiration is blocking other work or was stated as a prerequisite |

---

## Historian Advisor Integration

PathGraph feeds the Historian advisor via three outputs:

**1. Spirit Summary**

Per-lug summary of related aspirations, used by Historian at wakeup. Maps a lug_id to the originating session context and aspirations that motivated it.

Query: `get_spirit(lug_id)` → returns originating session + spirit summary

**2. Drift Report**

Module-level drift classification, surfaced at session start. Lists open aspirations per module, current drift level, and gap count.

Query: `get_drift_report(module)` → returns open aspirations, drift classification, gap count

**3. Ephemeral PRD**

Top aspirations + recommended action for session focus. Generated fresh at each session start. Expires at session end.

Query: `generate_ephemeral_prd(session_focus, module)` → returns top 3 aspirations, drift level, recommended next action

---

## Query Interface

```python
# Get spirit summary for a lug
def get_spirit(lug_id: str) -> dict:
    """
    Returns:
      - originating_session: str
      - spirit_summary: str
      - related_aspirations: list[dict]
      - fulfillment_status: str
      - drift_level: str | None
    """

# Get all aspirations for a spoke module
def get_aspirations(module: str) -> list[dict]:
    """
    Returns aspiration records ordered by recency x frequency.
    Filters: status, confidence, tags.
    """

# Check drift for a lug vs its originating aspiration
def check_drift(lug_id: str) -> dict:
    """
    Compares spec (lug target_files / acceptance_criteria) to
    originating aspiration. Returns drift_severity.
    """

# Get prior attempts on a topic
def prior_attempts(topic: str) -> list[dict]:
    """
    Returns previous attempts at this topic, outcomes,
    and reasons for abandonment.
    """

# Get drift report for a module
def get_drift_report(module: str) -> dict:
    """
    Returns:
      - open_aspirations: list[dict]
      - drift_classification: str
      - gap_count: int
    """

# Generate ephemeral PRD for session focus
def generate_ephemeral_prd(session_focus: str, module: str) -> dict:
    """
    Returns:
      - top_aspirations: list[dict]  (max 3)
      - drift_level: str
      - recommended_next_action: str
    Expires at session end. Regenerated next session.
    """
```

---

## Historian Workflow

The Historian follows a strict five-step workflow to transform track data into actionable design:

**Step 1 — Discover**

Read all conversation tracks, session notes, lugs, and teachings. Extract aspirations: what Mario said should exist, how things should feel, what goals were stated, what constraints were implied.

**Step 2 — Infer**

Build the inferred roadmap: ordered by what Mario said matters most, weighted by recency and frequency. Build the spoke profile: what this spoke should do, feel like, and deliver.

**Step 3 — Enumerate**

Enumerate the full spec — list every desired behavior, feature, and flow that can be inferred. Categorize as:

- `confirmed` — built and matches aspiration
- `drifted` — built but diverged from stated intent
- `missing` — stated but not built
- `aspirational` — mentioned but not yet scoped

**Step 4 — Gap Analysis**

ONLY after enumeration is complete and clear: perform gap analysis. Identify the delta between inferred roadmap and current reality. Rank gaps by: goal alignment × frequency mentioned × blocking other items.

Gap analysis before enumeration is prohibited. The sequence is enforced by the workflow.

**Step 5 — Remediation**

Produce remediation lugs for the highest-value gaps. Each lug treats the aspiration as inspiration — scope is shaped by Mario's goals, not just technical correctness.

---

## Existing Flow Protocol

When the Historian touches an existing flow, it follows a strict three-step sequence before proposing any change:

**Step 1 — Envision**: What does the Historian think Mario envisions for this flow? Extract from conversation traces and stated aspirations.

**Step 2 — Actual**: What does the actual code do? Read the implementation and note every divergence from the envisioned state.

**Step 3 — Optimize**: Design the optimization: align the flow with the vision. Produce design, code changes, and verification criteria together — not separately.

No optimization is proposed until Steps 1 and 2 are complete.

---

## Scout Swarm Role

Early scout swarms should be Historian-led: focused on discovery, aspiration extraction, and drift enumeration. No implementation happens until the Historian has produced a clear spoke profile and gap analysis.

Scout swarm output:

1. Spoke profile — what this spoke should do, feel like, and deliver
2. Full aspiration inventory — categorized by status
3. Gap analysis — ranked by goal alignment × frequency × blocking
4. Remediation lug queue — prioritized, implementation-ready

---

## Initial Seed

The archaeology output (`wilbur/docs/spoke-vision/`) serves as PathGraph's initial state. Each vision doc's "Verified Gap List" maps directly to drifted aspirations. The first PathGraph run should ingest these as high-confidence aspirations with `status = drifted`.

Modules with archaeology docs:

- `minder-core` — Supabase substrate gap, WAI-State context staleness
- `minder-telegram` — Tender inquiry listener non-functional
- `minder-web` — Tender page not retooled as fleet activity log aggregator
- `minder-forge` — PathGraph integration undesigned, no tests post-S66
- `minder-fleet` — Tender retool blocked on activity-log.jsonl schema
- `minder-ideas` — IdeaBank/ideas ambiguity, daily reminder cron status unknown
- `minder-tracks` — PathGraph integration undesigned, 14 incoming tracks unprocessed

---

## Periodic Refactor Trigger

The Historian refactors its spoke profile and aspiration index on a defined cadence:

- **Every 10 sessions** — incremental: add new aspirations, update drift levels
- **Every 30 sessions** — structural: re-evaluate aspiration categories, prune abandoned items
- **On major milestone** — full re-enumeration against current codebase state

Each refactor sharpens the inferred roadmap — it does not reset it. History is never deleted.

---

## Fleet Synthesis Layer (Wilbur only)

Wilbur's PathGraph has one capability no other spoke's PathGraph has: it reads from ALL spoke PathGraphs via hub-registry and synthesizes a cross-spoke view. This is the engine behind Wilbur's core mission — replacing Mario's manual operational overhead with an intelligent surface.

**How it works:**

1. At session start (or on demand), Wilbur reads each registered spoke's `WAI-Spoke/pathgraph/index.json` via hub-registry paths
2. Aggregates aspirations across spokes, grouped by team membership and dependency
3. Applies team priority weights (see Team Relationship Model below)
4. Produces a ranked recommendation: which spoke, which work, in what order, for Mario's next involvement

**Fleet synthesis outputs:**

| Output | Description |
|--------|-------------|
| `cross_spoke_surface` | Ranked list: spoke + work item + priority score + reason |
| `team_blocker_report` | Work in Spoke A that is blocking Spoke B within the same team |
| `drift_delta` | Aspirations that have drifted since last synthesis run |
| `mario_involvement_queue` | Items that require Mario specifically (decisions, gates, sign-offs) |

The `mario_involvement_queue` is Wilbur's primary output for replacing micro-management. Everything on this list is something only Mario can unblock — everything else Wilbur routes autonomously to the right spoke session.

---

## Team Relationship Model

Teams are named groupings of spokes that have meaningful interdependencies. Team membership informs how Wilbur weights cross-spoke work during fleet synthesis — work that advances multiple team members ranks higher than isolated work.

**Team definition file:** `wilbur/teams/{team-slug}.json`

```json
{
  "id": "product-build",
  "description": "Spokes that ship the product together",
  "members": [
    { "wheel_id": "minder", "role": "execution" },
    { "wheel_id": "wilbur", "role": "intelligence" },
    { "wheel_id": "framework", "role": "protocol" }
  ],
  "coupling": "tight",
  "priority_weight": 1.5
}
```

**Fields:**

| Field | Description |
|-------|-------------|
| `id` | Unique team slug |
| `description` | Human-readable description of why these spokes are grouped |
| `members[].wheel_id` | Must match a registered spoke in hub-registry |
| `members[].role` | Spoke's function within the team (free-form label) |
| `coupling` | `tight` (daily interdependency) \| `loose` (shared domain, less frequent) |
| `priority_weight` | Multiplier applied to cross-spoke work involving this team (default 1.0) |

**Declaring a team:**

Mario creates a team by adding a new file to `wilbur/teams/`. Wilbur reads this at synthesis time. Teams can overlap — a spoke can be in multiple teams.

**How Wilbur uses team context:**

When Mario says "I want to create a team and explain the relationships between spokes," Wilbur asks:
1. Which spokes?
2. What is their shared goal / interdependency?
3. Which spoke is the primary execution surface?

Then creates the team file and updates synthesis weighting. The next fleet synthesis run reflects the new priority structure.

**Team context in PathGraph aspirations:**

Aspirations can be tagged with `team_context: ["product-build"]` to indicate they are relevant to a specific team. Cross-team aspirations (e.g. a framework change that enables a minder feature) are tagged with both teams and ranked by combined weight.

---

## Evolution

PathGraph grows with each session. New track events are processed post-session. The index never shrinks — fulfilled aspirations are marked fulfilled, not deleted, to preserve history.

The Historian's perception model evolves continuously. Each refinement pass is a refinement, not a reset.
