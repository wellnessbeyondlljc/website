# Minder Spoke Vision — Index

**Generated:** 2026-05-25
**Source:** Session archaeology across 116 Minder sessions + codebase inspection
**Purpose:** PathGraph initial seed — baseline truth of intended vs. actual state per Minder module
**Status:** Draft — pending Mario review pass for accuracy verification

---

## Vision Documents

| Module | File | Status | Key Gap |
|--------|------|--------|---------|
| minder-core | [minder-core-vision.md](minder-core-vision.md) | draft | Supabase substrate not operational; WAI-State context stale |
| minder-telegram | [minder-telegram-vision.md](minder-telegram-vision.md) | draft | Tender inquiry listener non-functional when bot is in polling mode |
| minder-web | [minder-web-vision.md](minder-web-vision.md) | draft | Tender page not yet retooled as fleet activity log aggregator |
| minder-forge | [minder-forge-vision.md](minder-forge-vision.md) | draft | PathGraph integration undesigned; no tests post-S66 additions |
| minder-fleet | [minder-fleet-vision.md](minder-fleet-vision.md) | draft | Tender retool blocked on activity-log.jsonl schema (Basher work) |
| minder-ideas | [minder-ideas-vision.md](minder-ideas-vision.md) | draft | IdeaBank/ideas ambiguity; daily reminder cron status unknown |
| minder-tracks | [minder-tracks-vision.md](minder-tracks-vision.md) | draft | PathGraph integration undesigned; 14 incoming tracks unprocessed |

---

## Archaeology Summary

**Sessions scanned:** 116 total (Minder spoke) + framework sessions referencing Minder
**Primary focus:** Sessions from 2026-03-30 through 2026-05-25
**High-event sessions used:** session-20260415-1703 (12 events), session-20260403-2320 (9), session-20260518-0251 (8), session-20260406-2223 (8), session-20260406-0406 (8), plus 20+ additional sessions

**Codebase verified at:** `/home/mario/projects/minder/` (confirmed present, version 0.2.73, 116 sessions)

---

## Cross-Module Gaps (apply to all modules)

1. **Supabase `shared` project** — Mario needs to create it in dashboard. Until then, `_index.sync_enabled = false` and no fleet data syncs. This blocks fleet-level Wilbur features.
2. **PathGraph design missing** — Six of seven modules have PathGraph as an intended integration; no spec or lug exists for PathGraph itself. The archaeology revealed the need clearly. This is the next prerequisite for Wilbur.
3. **Activity-log.jsonl schema** — The fleet/tender retool requires standardized autopilot activity logs across all spokes (Basher-side work). Until this is standardized, the Tender page cannot aggregate fleet data.
4. **Navigator rate catalog** — Cost rollup in the Tender retool requires model rates from Navigator; Navigator must publish $/token rates before cost_usd column works.

---

## Mario Review Instructions

For each vision doc, please verify:
- "Current State" — is anything missing or wrong?
- "Intended State" — does this match your memory of what was decided?
- "Verified Gap List" — are any gaps wrong, resolved, or mischaracterized?
- "Open Threads" — are any of these actually decided/resolved?

Mark corrections directly in the doc. These documents become the first PathGraph seed once reviewed.
