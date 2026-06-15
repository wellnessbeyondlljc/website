# TasteGraph — Preference Model Specification

**Version:** 1.1.0
**Status:** Active
**Lug ref:** lug-tastegraph-spec-v1
**Schema:** `wilbur/schemas/tastegraph.schema.json`
**Seed data:** `WAI-Spoke/tastegraph.json`

---

## 1. Purpose and Scope

TasteGraph is the structured preference model for the Wilbur advisor system. It captures Mario's working preferences in a verifiable, learnable format so that every agent interaction reflects not just what to do, but _how_ Mario wants it done — at his preferred pace, risk posture, communication register, and aesthetic.

Without TasteGraph, agent execution is contextually correct but impersonally generic. TasteGraph is the subjective layer that turns correct execution into preferred execution.

**Scope:**

- Covers all preference dimensions that affect agent behavior: work style, communication, temporal patterns, risk tolerance, aesthetic, engagement, cost, accessibility, alignment gates, output format, trust, locale, and audience profile
- Grows continuously: stated preferences (seed) → inferred preferences (from revealed behavior) → verified preferences (confirmed by Mario)
- Does not capture project-specific knowledge — that lives in CLAUDE.md, WAI-State.json, and doctrine files

**Instance hierarchy:**

```
Hub TasteGraph (hub/tastegraph-org.json)
└─ Fleet defaults — applies to all spokes as a base

Wilbur TasteGraph (WAI-Spoke/tastegraph.json in Wilbur spoke)
└─ Authoritative Mario instance — the primary, most complete preference record
   Wilbur is the spoke whose mission is knowing Mario, so its TasteGraph is maintained
   most actively. Hub base derives FROM Wilbur's verified preferences, not the reverse.

Each other spoke (framework, minder, basher, ...)
└─ Extends hub base. May override spoke-specific preferences.
   Reads Wilbur's verified preferences via hub distribution when updated.
```

The resolution order at any spoke: spoke-local overrides → hub base (derived from Wilbur) → agent defaults.

---

## 2. Schema Definition

Every preference in TasteGraph is a single entry conforming to the following format.

**Preference Entry Fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string (slug) | yes | Unique preference identifier. Format: `{category-abbrev}-{kebab-description}` |
| `category` | enum | yes | One of the seven preference categories (see Section 3) |
| `key` | string | yes | Machine-readable key within the category. Used for programmatic lookup by advisors. |
| `value` | string \| boolean \| object | yes | The preference value. Type depends on category and key. |
| `confidence` | enum | yes | `stated` \| `inferred` \| `verified` — see confidence levels below |
| `source` | string | yes | Where this preference was derived from. Examples: `CLAUDE.md anti-patterns`, `session-20260525-1442`, `feedback_no_permission_asking.md` |
| `created_at` | ISO 8601 datetime | yes | When this preference was first recorded |
| `last_verified` | ISO 8601 datetime \| null | no | When Mario last confirmed this preference is still accurate. Null = never verified after creation. |
| `notes` | string \| null | no | Free-text notes. Capturing the original stated rationale or observed context is recommended. |

**Confidence Levels:**

- `stated` — Mario explicitly said this. Written directly in CLAUDE.md, feedback files, or a session conversation. Apply this preference as active.
- `inferred` — Wilbur derived this from observed behavior patterns across sessions. Must be proposed to Mario for verification before acting on it.
- `verified` — Mario was shown this preference and confirmed it accurately reflects his preference. The gold standard — apply autonomously with full confidence.

**Cardinal Rule:** A preference with confidence `inferred` may never be silently applied. It must be surfaced to Mario via the learning protocol (Section 5) and promoted to `verified` before autonomous use.

---

## 3. Preference Categories

### work_style
How Mario wants tasks structured and executed. Covers autonomy level, lug sizing, verification standards, scope discipline, and default execution posture.

Examples: autonomous execution preference, lug effort sizing bias, scope drift handling, verification-to-falsify standard.

### communication
How Mario wants to receive information. Covers message formatting, length, tone, level of ceremony, and structural preferences.

Examples: hash-border message format for user-facing updates, no markdown between borders, direct register with no hedging.

### temporal
When Mario works, at what intensity, and how sessions should be paced. Covers peak creative windows, protected idea time, session cadence, and attention budget per task type.

Examples: peak creative hours (10am–1pm Mon–Thu), preference for autonomous waves until human input required, protected thinking windows with no interrupts.

### risk_tolerance
How Mario balances speed versus safety across different decision domains. Covers technical debt acceptance, architectural stability, data safety, cost exposure, and timeline flexibility.

Examples: medium default risk tolerance (velocity over perfection), preference for waves of smaller lugs over large bets, P1 persistence rule (commit = done).

### aesthetic
Quality and craft preferences that shape what "good" looks like. Covers code style, documentation density, naming conventions, schema design, and structural elegance.

Examples: indexed subfolders over root dumps, non-prescriptive spoke implementations, teaching files for upgrades not standalone docs.

### engagement
How Mario prefers to interact with the system during a session. Covers vibe defaults, session opening posture, escalation thresholds, and human-in-the-loop vs. autonomous operation.

Examples: lead with refinement as session default (not build), only interrupt for destructive/irreversible actions, inbox review first every session.

### cost_sensitivity
How Mario wants AI compute resources allocated. Covers model routing defaults, weekly budget awareness, and lug-level model classification.

Examples: Sonnet as default, Haiku for extraction/classification, Opus only for complex multi-step reasoning or closeout, lug `model_fit` field drives routing.

### notification_preferences
When and how the agent surfaces information, alerts, and interrupts. Covers quiet hours, interruption thresholds, wave completion summaries, and error surfacing policy.

Examples: only interrupt for blockers or decisions requiring judgment, surface errors immediately, wave completion summary proactively.

### accessibility
Cognitive and sensory accommodations that shape how information is presented. Covers text density, paragraph length, formatting choices, and readability constraints.

Examples: short paragraphs (max 3 sentences), no walls of text, bold for key terms (dyslexia accommodation).

### alignment_gates
What requires an explicit sync or approval before the agent proceeds. Covers plan approval gates, topic alignment checks, scope confirmation, and direction change acknowledgment.

Examples: brief topic sync before building a plan; wait for approval before architectural decisions; autonomous for safe read ops only.

### output_format
How the agent structures and renders its responses for different contexts. Covers heading use, list depth, code block conventions, response length, and ceremony level.

Examples: hash borders for status updates, no markdown between borders, concise reporting style (what + key findings only).

### trust_ladder
Per-operation-type trust levels that determine autonomous vs. gated execution. A finer-grained extension of `risk_tolerance` scoped to specific action types.

Examples: read ops = autonomous; file edits within current scope = autonomous; architectural changes = gate; destructive ops = always confirm.

### locale
Language, formality, and cultural context preferences. Applies to both human-facing communication and agent-generated content.

Examples: English (default), casual-professional register, avoid jargon without definition.

### audience_profile
For output-facing TasteGraphs (e.g. website copy): who the generated content targets. Shapes vocabulary, tone, framing, and assumed knowledge level.

Examples: SaaS prospect (SMB owner, non-technical), technical buyer (senior engineer), community contributor.

---

## 4. File Format

TasteGraph data lives in a JSON file at `WAI-Spoke/tastegraph.json` (default collab graph) or `WAI-Spoke/tastegraphs/<name>.json` (named graphs for additional interfaces).

Top-level structure (v1.1.0):

```json
{
  "version": "1.1.0",
  "created_at": "<ISO 8601>",
  "updated_at": "<ISO 8601>",
  "spec_ref": "wilbur/docs/tastegraph-spec.md",
  "interface": {
    "id": "<slug>",
    "parties": ["<party-a>", "<party-b>"],
    "context": "<context-slug>",
    "description": "<human readable>",
    "parent_graph": "<path to org graph or null>"
  },
  "preferences": [ ... ]
}
```

**`interface` block fields:**

| Field | Description |
|---|---|
| `id` | Unique slug identifying this interface. Convention: `{user}-{counterpart}-{context}` |
| `parties` | Array of two parties in this communication relationship. Order: `[originator, receiver]`. Use `"agent"` for the AI side, user slug for the human side, `"prospect"` for outbound copy targets. |
| `context` | Slug describing the communication context. Examples: `personal-collaboration`, `website-copy`, `team-collab` |
| `description` | Human-readable description of when this graph applies |
| `parent_graph` | Relative path to parent (org-level) graph for nesting, or `null` if standalone |

The `interface` block is optional in v1.1.0 — files without it are assumed to be `parties: ["mario", "agent"]` for backward compatibility.

**Named graph convention:** Additional graphs for specific contexts live in `WAI-Spoke/tastegraphs/<context>.json`. The default collab graph stays at `WAI-Spoke/tastegraph.json`.

The `preferences` array contains preference entries conforming to Section 2. No deduplication logic is applied at read time — advisors must treat the last entry with a given `id` as canonical if duplicates exist (this should not happen in practice).

Schema validation: `wilbur/schemas/tastegraph.schema.json`

---

## 5. Learning Protocol

TasteGraph grows through two paths: manual authoring (stated) and Wilbur-observed inference (inferred→verified).

### 5.1 Manual Authoring (Stated)

A stated preference is recorded directly by the framework author or Mario during a session. Steps:

1. Identify the preference from CLAUDE.md, a memory file, or an explicit session statement.
2. Assign the appropriate `category` and `key`.
3. Set `confidence: "stated"`, `source` to the originating document, and `created_at` to now.
4. Append to `tastegraph.json`. No verification ceremony required — stated preferences are immediately active.

### 5.2 Wilbur Inference (Inferred → Verified)

When Wilbur observes a behavioral pattern across sessions that suggests an implicit preference, it creates a candidate inferred preference and surfaces it to Mario for review.

**Proposal format — single question:**

> "I noticed [observable pattern] across [N sessions/contexts]. Should I treat '[concise preference statement]' as a preference to apply going forward? (yes / no / modify)"

Rules for proposals:
- One preference per question. Never batch proposals.
- Include the observable evidence (sessions or contexts that triggered the inference).
- Offer a plain-language statement of the preference as Wilbur understands it.
- Accept three responses: `yes` (promote to verified), `no` (discard), `modify` (edit value then promote).

**After Mario responds:**

- `yes` → update entry: `confidence: "verified"`, `last_verified: <now>`. Preference is now active.
- `no` → remove entry from tastegraph.json. Do not re-surface.
- `modify` → capture Mario's corrected value, update entry, set `confidence: "verified"`, `last_verified: <now>`.

### 5.3 Verification Refresh

Preferences with `confidence: "verified"` should be re-surfaced for confirmation after 90 days without activity touching that domain. Wilbur tracks this via `last_verified`. A preference that was verified 90+ days ago is stale-verified, not expired — it remains active but should be re-confirmed at the next natural opportunity.

---

## 6. Verification Gate

**Rule:** A preference with `confidence: "inferred"` may never be autonomously applied.

This rule has no exceptions. The verification gate exists because inferred preferences are hypothesis — behavioral observations that have not yet been confirmed as intentional. Silently acting on an unverified hypothesis undermines trust in the system.

**Gate enforcement:**

- Before applying any preference to a decision, check `confidence`.
- `stated` or `verified` → apply.
- `inferred` → trigger the learning protocol (Section 5.2) at the next appropriate moment. Do not apply in the current session. Do not apply silently in any session.
- If a decision cannot be made without an inferred preference, escalate to Mario explicitly: "I have an inferred preference for X but it hasn't been verified — what would you prefer here?"

---

## 7. Query Interface

Advisors read preferences from `tastegraph.json`. The interface is intentionally simple — no database, no indexing layer.

**Standard read pattern:**

```python
import json

with open("WAI-Spoke/tastegraph.json") as f:
    tg = json.load(f)

preferences = {p["id"]: p for p in tg["preferences"]}
```

**Lookup by category:**

```python
def get_preferences(tg, category):
    return [p for p in tg["preferences"] if p["category"] == category]
```

**Lookup by key (within category):**

```python
def get_preference(tg, category, key):
    return next(
        (p for p in tg["preferences"] if p["category"] == category and p["key"] == key),
        None
    )
```

**Confidence filter (active-only):**

```python
def get_active_preferences(tg):
    return [p for p in tg["preferences"] if p["confidence"] in ("stated", "verified")]
```

Advisors should always use `get_active_preferences` as the baseline and only apply `stated` or `verified` entries.

---

## 8. Seed Preferences

The initial TasteGraph seed is populated from:

- `CLAUDE.md` — anti-patterns, standing rules, behavioral protocols
- `memory/feedback_*.md` — session feedback notes
- `memory/user_session_patterns.md`, `memory/user_preferences.md` — explicit user preference files
- Lug `minder_seed_preferences_to_capture` section from `lug-tastegraph-spec-v1.json`

Seed preferences all have `confidence: "stated"` — they were explicitly documented by Mario or the framework author as accurate observations.

The seed file is at `WAI-Spoke/tastegraph.json`. See that file for the full list of seed preferences.

---

## 9. Multi-Graph Model

A single user may maintain multiple TasteGraphs for different communication interfaces. Each graph declares its `interface.parties` and `interface.context` — the agent loads the appropriate graph based on context.

**Standard graphs:**

| File | Parties | Context | When loaded |
|---|---|---|---|
| `WAI-Spoke/tastegraph.json` | mario ↔ agent | personal-collaboration | Default: all development sessions |
| `WAI-Spoke/tastegraphs/website-copy.json` | agent → prospect | website-copy | When generating marketing/copy content |
| `hub/tastegraph-org.json` | org ↔ agent | team-collab | Team baseline; individual graphs inherit from it |

**Resolution order:** individual graph → parent_graph (org defaults) → hardcoded agent defaults.

Individual overrides are ADDITIVE. If an individual graph does not specify a category, the parent graph's value applies. Explicit overrides in the individual graph always win. There is no silent merge — overlapping keys resolve to the individual value.

**Loading logic:**

```python
def load_tastegraph(context="personal-collaboration"):
    named_path = f"WAI-Spoke/tastegraphs/{context}.json"
    if os.path.exists(named_path):
        return load_with_parent(named_path)
    return load_with_parent("WAI-Spoke/tastegraph.json")

def load_with_parent(path):
    graph = json.load(open(path))
    parent_path = graph.get("interface", {}).get("parent_graph")
    if parent_path and os.path.exists(parent_path):
        parent = json.load(open(parent_path))
        return merge_graphs(parent, graph)  # child wins on conflict
    return graph
```

---

## 10. Team Nesting

For multi-user teams, an org-level TasteGraph at `hub/tastegraph-org.json` sets shared defaults. Individual users extend it with their own overrides.

```
hub/tastegraph-org.json         ← team baseline (shared categories, defaults)
  WAI-Spoke/tastegraph.json     ← mario's overrides (parent_graph → hub/tastegraph-org.json)
  alice-spoke/WAI-Spoke/tastegraph.json  ← alice's overrides (e.g. locale: Spanish)
```

**Org graph responsibilities:** define the `communication.register`, `risk_tolerance.default`, `cost_sensitivity.model_routing` defaults shared by all team members. Individual members override only what differs for them.

The Historian mines each individual graph separately. Org-level changes require an explicit authoring session — the Historian never infers org preferences from a single user's behavior.

---

## 11. Injectable Prompt Export

Any TasteGraph can be serialized into a portable prompt block for use on any AI platform (claude.ai, chatgpt.com, custom API integrations).

**Export command:**

```
python3 tools/tastegraph_export.py [--graph <path>] [--format prompt|json|yaml]
```

Or via skill: `/wai-tastegraph export [--interface <id>] [--format prompt]`

**Design constraints for `--format prompt`:**

- Target: ~200 tokens (fits platform system prompt limits)
- Self-contained: no WAI-internal references, no path references, no jargon
- Human-readable by any AI: structured as plain instructions the AI can follow without WAI context
- Sections: header + one block per relevant category (omit empty/irrelevant categories)

**Example prompt output:**

```
[TasteGraph | mario ↔ agent | personal-collaboration | v1.1.0]

ACCESSIBILITY
• Short paragraphs only (max 3 sentences). Never write walls of text.
• Bold key terms. Avoid italics.

ALIGNMENT
• Offer a brief topic sync before building any plan. Wait for explicit approval before proceeding.
• Flag scope drift immediately. Require acknowledgment before changing direction.

COMMUNICATION
• Direct register. No hedging, no filler. Concise: what was done + key findings only.
• No trailing summaries after completing work.

TRUST
• Safe read ops: proceed autonomously.
• Architectural decisions, direction changes, destructive ops: always gate.

COST
• Default model: Sonnet. Extraction/classification: Haiku. Planning/closeout: Opus.
```

**Portability principle:** the exported block must be usable by GPT-4, Gemini, Claude, or any LLM without modification. It describes communication preferences in plain English, not WAI protocol.

---

## 12. Evolution

TasteGraph version is tracked in the file's `version` field (semver). Rules for version bumps:

- **Patch** (1.0.x) — new stated/verified preferences added, typo fixes, notes updates.
- **Minor** (1.x.0) — new categories added, schema fields added (backward compatible), new sections in spec.
- **Major** (x.0.0) — schema breaking changes, category renames, confidence level changes, interface block made required.

When the schema changes, update `wilbur/schemas/tastegraph.schema.json` in the same commit.

**Changelog:**

- `1.0.0` (2026-05-25) — initial spec + 20 seed preferences (work_style, communication, temporal, risk_tolerance, aesthetic, engagement, cost_sensitivity, notification_preferences)
- `1.1.0` (2026-05-28) — added `interface` block (optional), 6 new categories (accessibility, alignment_gates, output_format, trust_ladder, locale, audience_profile), multi-graph model (Section 9), team nesting (Section 10), injectable prompt export (Section 11)
