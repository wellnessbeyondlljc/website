# minder-fleet — Spoke Vision

**Module:** minder-fleet
**Last updated:** 2026-05-25
**Status:** draft (pending Mario review)

---

## Current State

The fleet module encompasses everything Minder does to monitor, coordinate, and maintain the health of the entire spoke ecosystem. It is partially built — the health infrastructure is live, the Gardener UI is operational, but the Tender page redesign (central fleet execution log) remains open.

**What exists today:**

Fleet health monitoring:
- `scripts/health_monitor.py` — three modes: full run (probe all spokes via hub-registry.json → store → Telegram synopsis → prune 90d results), spoke mode (--spoke, print only, no store), dry-run (--dry-run, discover only)
- `web/routes_status.py` — Blueprint: GET /status, GET /ops/health (Bearer-protected, 5-min background cache), GET /api/health/data, POST /api/health/ingest, POST /api/health/run
- `web/templates/status_page.html` — Fleet Status Page UI: fleet banner (worst-case rollup, last-checked, Run All), per-spoke expandable cards, 30-dot history strip with hover tooltips, stale-data warning when last run > 26h
- `src/minder/db/models.py` — HealthRun, HealthCheckResult tables
- `WAI-Spoke/health/statuschecks.json` — Minder's own health registration (web-server, database, telegram-bot checks)
- `cron-setup.md` — documents `0 7 * * *` crontab entry for health_monitor.py
- Nav dot indicator in `_nav.html` for RED/YELLOW fleet state

Gardener (fleet management UI):
- `web/gardener.py` — run_fleet_health_check(), _write_health_to_registry(), load_health_state(), run_characteristics_audit_with_routing()
- `web/routes_gardener.py` — GET /gardener, GET/POST/PATCH /api/gardener/*, PATCH /api/gardener/spokes/<id>/profile
- `web/templates/gardener.html` — tabs: Spokes (inline profile editing with team chips, stage, audience, urgency), Health (green/yellow/red status, Setup column with WAI adoption score), Characteristics, Tender History, Tender Report
- `scripts/gardener_synthesize.py` — POST /api/gardener/synthesize-learnings; detects cross-spoke patterns; outputs teaching proposals; Gemini + Z.AI fallback
- `data/health_state.json`, `data/characteristics_state.json` — cached fleet state

Spoke registry:
- Hub-registry.json is the authoritative spoke list (read via hub_path)
- 18+ active spokes registered (as of S62)
- Team chips per spoke (from spinner.inter_relation_groups)

Tender runner:
- `scripts/tender.py` — multi-spoke runner with Pass 0 (consistency audit), Pass 0.5 (edge-case scanner), Pass 2 (Claude/Gemini agent), Pass 2.5 (completion verification)
- `web/routes_tender.py` — tender execution UI, streaming log, spoke selection chips
- Sort order: framework first, hub last, others by last_tended desc (`sort_wheels()`)
- Fallback: FallbackClient switches Gemini → Z.AI on any API error for remainder of run

---

## Intended State

From session tracks (S62–S116), fleet coordination was identified as a central Minder responsibility: "Minder becomes the command center for fleet health."

Key design intentions:

1. **Fleet Status Page as trust anchor** — built and operational; Atlassian StatusPage-style, gives Mario confidence without per-spoke inspection
2. **Tender page as fleet activity log** — this is the open gap (lug `b70c2a7f95dd`, impact=7): retool from execution UI to aggregated autopilot run history. Shows every spoke's autopilot runs with model, tokens, cost, lug outcomes; filterable. Requires activity-log.jsonl schema standardization (Basher-side prerequisite `d74879881d4d`).
3. **Gardener as spoke control surface** — fully realized in S62-S65; spoke profile editing, team management, urgency buttons all wired to WAI-State.json as primary source (hub registry as secondary)
4. **Health endpoint template for all spokes** — the fleet status lug included a reusable lug template (`feature-spoke-health-registration-template-v1`) for each spoke to implement `/ops/health`; this was part of the plan but the template lug's delivery status is unknown.
5. **Gardener synthesize learnings** — the cross-spoke pattern detector was intended to eventually propose framework teachings automatically; currently it detects and outputs proposals but doesn't auto-deliver
6. **Stuck-spokes detection** — S102 added WARN×3 escalation + stuck-spokes UI to Gardener (when a spoke has consecutive WARN grades, it appears in a dedicated stuck-spokes panel)

---

## Verified Gap List

- **Tender page not retooled**: Open lug `b70c2a7f95dd` (feature, impact=7) — execution UI needs to become fleet activity log aggregator. Dependency on `d74879881d4d` (activity-log.jsonl schema) first.
- **Health endpoint registration across spokes**: Only Minder itself has a `WAI-Spoke/health/statuschecks.json`. The fleet-wide rollout template (`feature-spoke-health-registration-template-v1`) — verify if this lug was ever created and delivered to spokes.
- **HEALTH_CHECK_SECRET not fleet-wide**: Each spoke needs this in their `.env.local`. The signal `signal-fleet-secrets-template-audit-v1` (open) tracks this gap.
- **Gardener synthesize learnings → teaching delivery**: The synthesize learnings feature (S102) produces proposals but the delivery path to hub teachings/ is manual, not automated.
- **Surveyor cross-dependency**: `tools/surveyor_report.py` reads hub data paths. Hub path is configured via `hub_path` in WAI-State.json — if hub moves, Surveyor breaks.
- **18 spokes but health data coverage unknown**: Health monitor can only probe spokes that have `/ops/health` endpoints. Unknown how many of the 18 registered spokes have this implemented.

---

## Open Threads

- Activity-log.jsonl schema standardization (fleet-wide Basher work) — prerequisite for Tender retool
- Health endpoint rollout — needs a delivery mechanism to push statuschecks.json template to all active spokes
- Cost tracking: the Tender activity log design includes cost_usd rollup (tokens × model rate from Navigator catalog). Navigator rate catalog must be available before cost column works.
- Fleet-wide Supabase sync: when `_index.sync_enabled = true`, the fleet index substrate becomes operational; all health + activity data could sync to shared Supabase project. Currently blocked on Mario creating the Supabase project.
