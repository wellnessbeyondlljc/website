# Historian Advisor — PathGraph Configuration

**Advisor:** Historian (`WAI-Spoke/advisors/historian/`)
**PathGraph integration:** initial_sweep mode + runtime query mode
**Created:** 2026-05-25
**Lug:** lug-pathgraph-advisor-spec-v1

---

## initial_sweep Mode

Run once after PathGraph is seeded from archaeology output. Steps:

1. Read all 7 spoke-vision docs from `wilbur/docs/spoke-vision/`
2. Extract gap lists as drifted aspirations → seed `wilbur/pathgraph-index.json`
3. Run drift detection pass across all modules
4. Write initial drift report to `wilbur/pathgraph-initial-drift-report.json`

Each vision doc's "Verified Gap List" maps directly to drifted aspirations. Ingest as `confidence: "explicit"`, `status: "drifted"`.

Modules to ingest:

| File | Module |
|------|--------|
| `minder-core-vision.md` | minder-core |
| `minder-telegram-vision.md` | minder-telegram |
| `minder-web-vision.md` | minder-web |
| `minder-forge-vision.md` | minder-forge |
| `minder-fleet-vision.md` | minder-fleet |
| `minder-ideas-vision.md` | minder-ideas |
| `minder-tracks-vision.md` | minder-tracks |

---

## Runtime Query Mode

At each session wakeup:

1. Determine session focus from WAI-State or user's opening prompt
2. Query PathGraph for top 3 aspirations matching focus module (ordered by weight = recency x frequency)
3. Get current drift level for that module
4. Generate ephemeral PRD → surface in Historian's wakeup output

---

## Output Format (at wakeup)

```
HISTORIAN — PathGraph
  Module: minder-core | Drift: significant
  Top aspirations:
    1. [explicit] "Tender should page advisors sequentially, not batch" (session-20260401-1200)
    2. [explicit] "Wakeup brief under 12k tokens" (session-20260415-1703)
    3. [inferred] "Activity log standardized before Tender retool" (session-20260523-0900)
  → Recommended: Address activity-log.jsonl schema before any Tender work
```

Output only when PathGraph index has records for the session focus module. Omit block if index is empty or module has no open aspirations.

---

## Data Files

| File | Description |
|------|-------------|
| `wilbur/pathgraph-index.json` | Aspiration records (created by initial_sweep) |
| `wilbur/pathgraph-initial-drift-report.json` | First drift report after initial_sweep |
| `wilbur/schemas/pathgraph-index.schema.json` | JSON Schema for individual aspiration records |
| `wilbur/docs/pathgraph-spec.md` | Full PathGraph specification and protocols |
| `WAI-Spoke/advisors/historian/advisor.json` | Historian advisor configuration |
| `WAI-Spoke/advisors/historian/SPEC.md` | PathGraph integration spec for this advisor |
| `WAI-Spoke/advisors/historian/ephemeral-prd-template.md` | Template for generating ephemeral PRDs |
