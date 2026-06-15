# WAI Initiative + Theme Tracker

Surface the 7-dimension health scorecard and initiative groupings. Shows which dimensions are improving, neglected, or unscored. Used to ensure epics are addressing the right concerns.

---

## Trigger

User runs `/wai-initiative` or asks "show me the theme scorecard" or "which themes are neglected?"

---

## Purpose

The 7 health dimensions (themes) are the measuring stick for whether the project is improving in the right ways. Epics should tag the dimensions they address — this skill surfaces the coverage map so neglected dimensions are visible and scoring stays current.

---

## Priority Contract

Initiatives in `lifecycle_state: approved | active | measuring` are **Tier 0 (time-sensitive)** work. Ozi exhausts all Tier 0 lugs before dispatching any Tier 1 (backlog) work.

**Lookup chain:** lug `parent_epic` → epic `initiative_id` → initiative `lifecycle_state`

- `proposed` and `complete` initiatives: Tier 1 (not time-sensitive)
- Within Tier 0: normal `urgency → ROI → wave` ordering applies
- `focus_lock=true`: controls which Tier 0 initiative sorts first (3× ROI boost on focus-locked lugs, still within Tier 0)
- When all Tier 0 work is blocked or stalled: Ozi proceeds to Tier 1 automatically

**Tuning:** The qualifying lifecycle states are configured in `WAI-Spoke/lugs/bytype/spec/open/spec-initiative-priority-v1.json` → `config.tier0_lifecycle_states`. Edit that file to change tier rules — do not edit the Python tools directly.

**Prerequisite for Tier 0 promotion:** Every epic lug must have `initiative_id` set to its parent initiative's `id`. Epics without this field land in Tier 1 regardless of the initiative's lifecycle state.

---

## Output Format

### Theme Scorecard

For each theme: `id | label | description (brief) | score (or "unscored") | last_graded (or "never")`

Read from `WAI-Spoke/health/themes.json` (canonical). Fallback: `WAI-Spoke/initiatives/index.json` → `themes[]` if `health/themes.json` absent.

- Highlight themes with `score: null` as **needing grading**
- Highlight themes with no active epic coverage as **neglected dimension**
- Sort: unscored + neglected first, then by score ascending

```
Theme Scorecard
  quality        | Code and architecture health    | 7.5 | graded 2026-04-01
  enablement     | Tooling and process health      | 6.0 | graded 2026-03-15
  growth         | Capability expansion            | unscored | never          ⚠ needs grading
  impact         | Measurable user/business value  | 5.0 | graded 2026-03-01 ⚠ no active epics
  performance    | Speed and reliability           | unscored | never          ⚠ needs grading
  awareness      | Observability and monitoring    | 8.0 | graded 2026-04-10
  satisfaction   | User and developer satisfaction | unscored | never          ⚠ needs grading
```

### Initiative Groups

For each initiative in `WAI-Spoke/initiatives/bytype/initiative/{lifecycle_state}/*.json` (per-file, canonical). The generated read-model `WAI-Spoke/initiatives/index.json` → `initiatives[]` may also be used as fallback.

```
Initiatives
  wilbur-foundation | In Progress | 3 epics
    epic-a3f7b2c  Lug validation baseline          [in_progress]
    epic-09fd21cc Schema normalization enforcement  [open]
    epic-b4e8f1a  Outbound monitoring wiring        [completed]

  wave-2-growth | Planned | 2 epics
    epic-c1234de  Tastegraph spec integration       [in_progress]
    epic-f5678ab  Navigator advisor rollout          [open]
```

Epic statuses are read from `WAI-Spoke/lugs/bytype/epic/`. Cross-reference `initiative_id` on each epic lug.

### Coverage Gaps

Report two categories:

1. **Epics with no theme tags** — epics missing the `themes` field entirely
2. **Themes with no active epics** — themes where zero open/in-progress epics reference them

```
Coverage Gaps
  Epics missing theme tags (3):
    epic-09fd21cc  Schema normalization enforcement
    epic-f5678ab   Navigator advisor rollout
    epic-c1234de   Tastegraph spec integration

  Themes with no active epics:
    growth, performance, satisfaction
```

### Scoring Guide

Scores are 1-10. Grade a theme by reviewing all epics tagged to it and the outcomes delivered.

- 1-3: Actively degrading — regressions, unresolved debt
- 4-6: Stable but not improving — maintenance mode
- 7-8: Actively improving — recent epics landed
- 9-10: Excellent — strong coverage, recent validated wins

**Grading cadence:** Monthly or after a major epic completes.

---

## Data Sources

| Data | Source |
|------|--------|
| Theme definitions + scores | `WAI-Spoke/health/themes.json` (canonical) |
| Initiative groups | `WAI-Spoke/initiatives/bytype/initiative/{lifecycle_state}/*.json` (per-file canonical); `index.json` is the generated read-model |
| Epic statuses | `WAI-Spoke/lugs/bytype/epic/{status}/*.json` |
| Epic theme tags | `themes` field on each epic lug |
| Epic initiative membership | `initiative_id` field on each epic lug |

Cross-reference: for each theme, collect all epics whose `themes` array includes that theme ID and whose status is `open` or `in_progress`. That set is the theme's "active coverage."

---

## Sub-Commands

### `/wai-initiative score <theme-id> <score>`

Record a new score for a theme.

1. Read `WAI-Spoke/health/themes.json`
2. Find the theme by `id`
3. Set `score` to the provided integer (1-10)
4. Set `last_graded` to today's date (ISO 8601)
5. Write back to `WAI-Spoke/health/themes.json`
6. Confirm: `"quality scored 7.5 — graded 2026-05-25"`

Validation: score must be 1-10. Reject anything outside range.

### `/wai-initiative tag <epic-id> <theme1> [theme2...]`

Add theme tags to an epic lug.

1. Find the epic lug file at `WAI-Spoke/lugs/bytype/epic/{status}/{epic-id}.json`
2. Read current `themes` field (may be missing or empty)
3. Merge new themes into existing list (deduplicate)
4. Validate all themes against the 7 valid values
5. Write updated lug back
6. Confirm: `"epic-09fd21cc tagged: [quality, enablement]"`

Valid theme IDs: `quality` | `growth` | `impact` | `enablement` | `performance` | `awareness` | `satisfaction`

### `/wai-initiative group <initiative-id>`

Show detail for one initiative.

Display:
- Initiative label, description, status
- All epics in the initiative with: id, title, status, themes, estimated completion
- Whether the initiative is "complete" (all epics at `completed` status)
- Any epics missing `themes` tags

---

## Implementation Notes

- If `WAI-Spoke/initiatives/index.json` does not exist: display `"No initiatives index found — create WAI-Spoke/initiatives/index.json to use this skill."` and stop.
- An initiative is complete only when **all** its epics reach `completed` status.
- An epic with 4+ theme tags likely has unclear scope — surface as a note, not a hard error.
- Theme imbalance threshold: any single theme with 3x more active epics than another non-zero theme is worth flagging.

---

## Related Skills

- `/wai` — Full wakeup briefing (includes epic summary)
- `/wai-status` — Quick health check
- `/wai-closeout` — End session (may prompt for theme scoring if epics completed)
