# Wilbur — Project Charter

**Project:** Wilbur Intelligence Layer
**Spoke:** Minder (framework-designed)
**Created:** 2026-05-25
**Foundation phase:** epic-wilbur-foundation-phase-v1

---

## What Wilbur Is

Wilbur is the intelligence layer for Minder — a system of three interlocking components that make each session smarter than the last:

| Component | Role |
|-----------|------|
| **PathGraph** | Session history index — extracts aspirations, detects drift, feeds Historian |
| **TasteGraph** | Preference model — captures and verifies Mario's working preferences |
| **Intelligence Loop** | Autonomous optimization cycle — ROI-gated, runs at session-start/background/closeout |

---

## What Wilbur Is Not

- Not a replacement for the WAI session protocol
- Not an autonomous agent that makes decisions without user oversight
- Not a data store — Wilbur indexes and surfaces, it does not own canonical data
- Not a replacement for lugs — lugs are the work record, Wilbur reads them

---

## Doctrine

1. **ROI-gated** — every optimization requires projected ROI > cost before running
2. **Verification-first** — inferred preferences never silently applied
3. **Additive** — Wilbur adds context, never removes or overrides existing protocol
4. **Transparent** — every Wilbur surface shows its data source and confidence
5. **Propagation over piecemeal** — improvements ship as coherent waves across all affected areas, not one touch point at a time

---

## Architecture

```
wilbur/
├── CHARTER.md                        ← you are here
├── optimization-backlog.json         ← ROI-gated improvement queue
├── docs/
│   ├── intelligence-loop-spec.md     ← 8-step reasoning cycle + session lifecycle
│   ├── tastegraph-spec.md            ← preference model schema + lifecycle
│   ├── tastegraph-notification-preferences-spec.md
│   ├── pathgraph-spec.md             ← aspiration index + drift detection
│   ├── pathgraph-historian-config.md ← Historian advisor config
│   ├── notification-escalation-spec.md
│   ├── notification-preferences-spec.md
│   ├── propagation-plan-template.md  ← format for Step 8 output
│   └── spoke-vision/                 ← 7 module vision docs (archaeology baseline)
└── schemas/
    ├── tastegraph.schema.json
    ├── pathgraph-index.schema.json
    ├── escalation-routing.schema.json
    └── optimization-backlog.schema.json
```

Runtime data lives in `WAI-Spoke/`:
- `WAI-Spoke/tastegraph.json` — live preference store (21 seed preferences)
- `WAI-Spoke/advisors/historian/advisor.json` — Historian advisor config

---

## Foundation Phase Deliverables

| Deliverable | Status |
|-------------|--------|
| Wilbur project scaffold | completed |
| Session archaeology (spoke vision docs) | completed |
| TasteGraph spec + seed preferences | completed |
| TasteGraph notification preferences | completed |
| PathGraph spec + Historian config | completed |
| Lug commitment accounting | completed |
| Lug QC two-pass system | completed |
| Intelligence loop spec | completed |
| Notification escalation spec | completed |

---

## Key Design Decisions

**Why accumulate before surfacing?** Trust is earned by not being noisy. Every agent that surfaces every idea immediately trains the user to ignore it. Wilbur holds improvements until their combined ROI justifies the interruption — then surfaces a coherent batch. This is the trust-building mechanism.

**Why propagation waves?** A single improvement in one module while adjacent modules remain inconsistent creates confusion and technical debt. Wilbur identifies all tangential areas at discovery time and proposes them together. Mario ratifies the full wave or defers specific areas — but the decision is made consciously, not silently.

**Why ROI-gated?** Token spend, time, and attention are finite. Wilbur's value is proportional to its signal-to-noise ratio. An ROI threshold that adjusts dynamically to TasteGraph attention budget preferences ensures Wilbur is always a net positive to a session, never a drain.

---

## Next Phase

Phase 2 will implement PathGraph indexing (actual track ingestion) and TasteGraph verification flows.

See `wilbur/docs/` for all specs.
