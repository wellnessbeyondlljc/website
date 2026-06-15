# minder-web — Spoke Vision

**Module:** minder-web
**Last updated:** 2026-05-25
**Status:** draft (pending Mario review)

---

## Current State

The web module is a Flask application running on port 5001 with a comprehensive multi-module UI. It is the primary command surface for everything Telegram cannot handle.

**What exists today (web/app.py — registered blueprints):**
- `routes_delivery` — item delivery to spokes
- `routes_tracks` — Track Vault (track ingestion, exploration, scan, WAI track API)
- `routes_tender` — Tender page (spoke selection, run trigger, streaming log)
- `routes_gardener` — Gardener (fleet health, characteristics audit, synthesize learnings, spoke profile editing)
- `routes_realizer` — Realizer (goal loop, hypothesis management, evidence scoring, intervention dispatch)
- `routes_surveyor` — Surveyor fleet dashboard (Minder-hosted, reads hub data)
- `routes_coo` — Orko COO agent (context API + chat endpoint)
- `routes_auto_routing` — track auto-routing
- `routes_forge` — Forge (Knowledge Base module — KB browser, Ask, Review queue, Sources, Capture, Deploy Lug)
- `routes_feedback` — UAT feedback (scan bytype/ for uat-*.json, action endpoint)
- `routes_status` — Fleet Status Page (/status, /ops/health, /api/health/*)
- Core app routes: `/` (content hub), `/library`, `/library/<item_id>`, `/library/bulk`, `/library/new`

**Templates (web/templates/):**
- `index.html` — content hub / library landing
- `item_detail.html` — per-item detail + Orko refinement chat
- `bulk_intake.html` — bulk idea intake
- `content_hub.html` — content hub view
- `forge.html` — Forge KB UI (4 sections: Overview, Review, Search, Sources)
- `gardener.html` — Gardener fleet UI (tabs: Spokes, Health, Characteristics, Tender History, Tender Report)
- `realizer.html` — Realizer goal loop UI
- `realizer_dashboard.html` — Realizer dashboard
- `surveyor.html` — Surveyor fleet dashboard
- `tender.html` — Tender execution UI (streaming console, spoke selection chips, run summary panel)
- `status_page.html` — Fleet status health dashboard
- `tracks.html` — Track Vault main listing
- `track_explore.html` — Track Explorer (paste, explore, extract items)
- `feedback.html` — UAT feedback review
- `_coo_panel.html` — Orko COO floating panel (included in layout.html, every page)
- `_nav.html` — global nav (Track Vault | Forge | Surveyor | Tender | Gardener | Realizer | Status)
- `layout.html` — base layout with Tailwind CDN (Play CDN v3, JIT), Orko CSS theme

**Design system:**
- `web/static/css/orko-theme.css` — canonical design tokens (:root variables)
- Per-module extracted stylesheets: `index.css`, `coo-panel.css`, `item_detail.css`, `realizer.css`, `forge.css`
- `web/static/js/library.js` — shared JS (renderSpokeToggles, getSelectedSpokes)
- `web/static/js/fleet-helpers.js` — fleet spoke helpers

**Server-side body classes** prevent CLS; template-driven classes render before first paint.

**Tests:** 580+ passing as of S113; pytest with Flask test client.

---

## Intended State

From session tracks across S62–S116, the web module was always intended to grow into a **full command center** — not just a library UI. Key design intentions:

1. **Single-page-per-module navigation pattern** — each module (Forge, Gardener, Tender, Realizer, Surveyor, Status) is its own route with a consistent nav; Orko COO floats across all of them
2. **COO as cross-module consciousness** — the Orko COO panel was explicitly designed to have module-specific context (`window.COO_PAGE_CONTEXT`), auto-open with fresh brief on arrival at module pages, and persist across navigation via sessionStorage
3. **Tender page identity shift** — the Tender page was originally an execution UI; the design intent (open lug `b70c2a7f95dd`) is to retool it as a **fleet activity log aggregator** — read-only visibility into autopilot run history, filterable by spoke/model/trigger/outcome, with cost rollup. The execution capability stays in Realizer.
4. **Realizer as intelligence hub** — the Realizer module was designed to evolve from observation → judgment → reuse (post-MVP epic). The web UI is its primary surface.
5. **Status page as trust layer** — the Fleet Status page (built S111+) gives Mario confidence that all spokes are healthy, without needing to check each one individually.
6. **Gardener as spoke control surface** — Gardener was deliberately expanded in S62 to handle spoke profile editing, team management, and characteristics audit in addition to health checks.
7. **gzip compression** — deferred; WSL venv path split prevents C-extension packages. Status: use stdlib-only middleware or production reverse proxy. Documented in context.insights.

---

## Verified Gap List

- **Tender page not yet retooled**: The open lug (`b70c2a7f95dd`, feature, impact=7) specifies a full redesign as fleet activity log aggregator. Currently still shows execution controls. Depends on lug `d74879881d4d` (activity-log.jsonl schema standardization).
- **gzip not shipped**: Documented constraint (WSL venv path split). Acknowledged workaround: reverse proxy.
- **Orko COO module nav row**: S80 added module nav chips in COO panel (All/Gardener/Tender/Surveyor/Realizer) — Forge and Status were added later; verify they are wired into the COO context gathering.
- **Lighthouse scores**: `scripts/lighthouse-audit.mjs` present; last run results in `lighthouse-reports/`. Failing audits not tracked in lug system.
- **Surveyor ownership**: Surveyor was transferred from hub to Minder in S77. The `tools/surveyor_report.py` still reads hub data paths — this cross-dependency is load-bearing and fragile.

---

## Open Threads

- Tender page identity: finalize as activity log aggregator — requires activity-log.jsonl schema standardization fleet-wide (Basher-side work) before Minder can aggregate
- COO context gathering for Forge and Status modules — confirm `routes_coo.py` has `_gather_forge_context()` and `_gather_status_context()` equivalents
- Wilbur integration point: The Feed will eventually surface through the web UI — design for this is not yet specified
- `epic-orko-chat-upgrade-v1` is open — Orko Chat upgrade (web + Telegram) not yet executed
