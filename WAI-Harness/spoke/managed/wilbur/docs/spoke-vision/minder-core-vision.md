# minder-core — Spoke Vision

**Module:** minder-core
**Last updated:** 2026-05-25
**Status:** draft (pending Mario review)

---

## Current State

The core session loop is fully operational. Minder runs as a Flask web server (`./start_minder.sh`, port 5001) with a Python 3.11 stack backed by SQLite (async via SQLAlchemy + aiosqlite), Gemini 2.0-flash/2.5-pro for LLM tasks, and Z.AI (GLM-4.5) as the fallback provider.

**What exists today:**
- `src/minder/main.py` — entry point, orchestrates bot + web server startup
- `src/minder/config.py` — configuration loader; reads `.env.local`
- `src/minder/env.py` — env var resolution
- `src/minder/db/` — SQLAlchemy models; HealthRun, HealthCheckResult, and item tables
- `src/minder/storage/` — Markdown sidecar storage for items
- `src/minder/llm/` — GeminiClient + ZaiClient wrappers
- `src/minder/scheduler/` — task scheduler stubs
- `src/minder/logging/` — audit + minder loggers
- `WAI-Spoke/` — full Wheelwright state (WAI-State.json, lugs, sessions, advisors)
- `scripts/tender.py` — multi-spoke tender runner (Pass 0 consistency audit → Pass 2 Claude/Gemini agent → Pass 2.5 completion verification); FallbackClient wraps Gemini with Z.AI fallback for remainder of run on any API error
- `wai-enter.sh` / `wai-exit.sh` — session lifecycle hooks
- `.env.local` — environment variables (GOOGLE_API_KEY, ZAI_API_KEY, TELEGRAM_BOT_TOKEN, HEALTH_CHECK_SECRET, TELEGRAM_CHAT_ID)
- `WAI-Spoke/advisors/` — advisor registry including ozi, gardener, navigator, historian, octo, quartermaster, qa-guardian, cc-advisor, expediter, archie
- Session count: 116 (as of session-20260524-2304)
- Version: 0.2.73

**Core capture pipeline (original intent, proven operational):**
> Capture → LLM classification (task/idea/reference) → auto-tag → similar-item lookup → append or new → confirmation → Git auto-commit

**Quality gates in place:**
- `scripts/tender.py` Pass 0.5 edge-case scanner (auto-fix before AI session)
- Post-Claude completion verification (reopens lugs with missing target_files)
- Tender nightly auto-commit per spoke after items_completed > 0
- `scripts/health_monitor.py` — daily cron at 07:00 UTC probes spoke health endpoints
- `WAI-Spoke/_hooks/` — session-start.sh, pre-tool-guard.sh, post-tool-use.sh hooks

---

## Intended State

From session tracks (S59–S116), the intended core loop was:

1. **Near-zero capture friction** — thought to saved in < 3 seconds (Telegram path: proven. Web path: operational but slower)
2. **Proactive tender** — nightly runs that auto-adopt teachings, route mail, execute ready lugs, auto-commit, and send Telegram synopsis
3. **Self-healing data** — Git-backed, monitored, with auto-retry on degraded quality
4. **COO awareness** — persistent Orko COO panel that gives Mario a live executive brief of system state from any page
5. **Full multi-provider LLM resilience** — Gemini primary, Z.AI (GLM-4.5) fallback, no single point of failure
6. **Session tracks as permanent record** — every turn tracked in JSONL, sessions indexed, accessible via web UI

The broader design aspiration from S116/wilbur-vision.md: Minder should eventually be Wilbur's substrate — the platform that holds all behavioral signals, the gateway through which WAI observes Mario's patterns, and the command surface for the Wheel.

---

## Verified Gap List

- **Supabase substrate not operational**: `_index.sync_enabled = false`. Migration plan exists (`spec-shared-platform-multi-tenant-db-v1`) but Supabase project `shared` needs Mario to create it in dashboard first. Fleet index cannot sync until this is resolved.
- **TELEGRAM_CHAT_ID setup dependency**: Tender Telegram inquiry listener competes with aiogram polling for getUpdates — bot in polling mode consumes updates before tender can read them. Summary sends work; inquiry listener is non-functional when bot is running.
- **Advisor schema adopted but Supabase not configured**: `advisor_manager.py` installed, schema YAML present, but `sync_enabled = false` so advisors are local-only.
- **Context WAI-State.json is stale** (captured March 2026 era context, not S116). The `context.current_phase` field does not reflect current state.
- **KnowMe.md**: Last generated S80 (2026-04-08) — not current.
- **Wakeup brief staleness detection**: `signal-wakeup-brief-smart-staleness-v1` was copied to processed as N/A for this spoke — brief caching is not SHA-based.

---

## Open Threads

- Supabase `shared` project creation (blocked on Mario dashboard action) — `_savepoint` in WAI-State.json tracks this
- `epic-realizer-post-mvp-intelligence-roadmap-v1` — marked completed but needs impl lug breakdown per S116 closeout
- S117 recommendation: process 2 teachings (semantic-verification-count + ozi-autopilot), then resume Supabase setup
- Design question: when bot is in polling mode, how should Tender's inquiry listener work? Currently unresolved — tender-inbox.jsonl approach exists but the bot consumes updates first.
