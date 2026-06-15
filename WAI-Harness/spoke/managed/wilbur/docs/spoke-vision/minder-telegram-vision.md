# minder-telegram — Spoke Vision

**Module:** minder-telegram
**Last updated:** 2026-05-25
**Status:** draft (pending Mario review)

---

## Current State

The Telegram module is the primary capture interface for Minder. It is fully operational as the fastest path from thought to storage.

**What exists today:**
- `src/minder/telegram/bot.py` — aiogram 3.4.0 bot, polling mode
- `src/minder/telegram/handlers.py` — item capture state machine (AddItemState: awaiting_lookup → awaiting_confirmation), idea intake (IdeaIntakeState), COO chat state, Orko conversation state
- `src/minder/telegram/idea_intake.py` — IdeaIntakeService; routes ideas through local ideas/ repo with why_bother capture
- `src/minder/telegram/item_actions.py` — ItemActionsMixin; append, defer, done callbacks
- `src/minder/telegram/track_receiver.py` — WAI-CHUNK N/M text ingest; routes bot-side track uploads ahead of generic text capture
- `src/minder/telegram/track_upload.py` — file upload handler for .jsonl track files
- `src/minder/telegram/utils.py` — keyboard builders, markdown escaping
- `start_bot.sh` — standalone bot launch script
- `src/minder/forge/telegram_handlers.py` — `/refresh`, `/forge digest` Telegram commands (part of Forge module, wired into bot)
- Tender Telegram integration: `scripts/tender.py` sends nightly synopsis via sendMessage after each full run; `_telegram_poll_inquiries()` polls for user inquiries post-run

**Operational capabilities:**
- Text message capture → LLM classification (task/idea/reference) → auto-tags → similar entry lookup → append/new choice → auto-add on 60s timeout
- File upload → .jsonl track ingestion → indexed in tracks/
- WAI-CHUNK N/M chunked text ingest (for long track pastes from Telegram)
- COO chat mode — Telegram as entry point to Orko COO agent
- Idea intake — structured capture with why_bother → local ideas/ repo → status flow (new → draft → approved → delivered)
- Tender inquiry listener — post-run Q&A (functional when bot is NOT in polling mode)
- Forge commands — `/refresh` (stale node refresh), `/forge digest` (daily digest)
- Time-aware Orko greeting (morning/afternoon/evening/late-night)
- UAT feedback via Telegram — daemon thread pings on every UAT submission

**Tests:** 101+ passing async tests for Telegram/handler/track slice

---

## Intended State

From session tracks (S59–S80, S108+), the Telegram module was always intended as the **zero-friction capture surface** — the interface that requires the least deliberate effort from Mario.

Key intentions identified in sessions:

1. **State machine is the right pattern** — the current lookup→confirmation flow was explicitly decided in S45-ish sessions; the aiogram 3.x FSM approach is intentional, not incidental
2. **WAI-CHUNK ingest is a first-class path** — `track_receiver.py` is the deliberate handling of bot-side [WAI-CHUNK N/M] messages; cannot be synthesized via Bot API (external operator check only)
3. **Inquiry listener design tension unresolved** — bot polling mode consumes getUpdates before tender can read them; the `tender-inbox.jsonl` file-based approach was the workaround but remains non-functional in practice
4. **Telegram as COO command surface** — COO panel was explicitly extended to Telegram as a channel, not just web (S78 session design)
5. **Idea intake Orko flow** — progressive saves (emit as learned, not on approval) — decided in S~60 range after Gemini multi-line JSON bug was fixed

---

## Verified Gap List

- **Tender inquiry listener non-functional** when bot is in polling mode (both consume getUpdates, bot wins). No resolved design yet — `tender-inbox.jsonl` workaround exists but isn't being used actively.
- **TELEGRAM_CHAT_ID setup**: must be in `.env.local` directly (not from `config.py` which only exposes bot_token). Tender uses raw httpx and needs the numeric chat ID. This is documented in context.insights but may catch future agents.
- **Track upload auto-routing not verified e2e**: transport-level proof for [WAI-CHUNK N/M] path requires external operator check (cannot be synthesized through Bot API). Status: documented as known gap.
- **Bot polling vs. webhook mode**: currently polling (start_bot.sh). No webhook mode implemented. For production deployment with proper inquiry listener, webhook would be needed.
- **Forge Telegram handlers not in main handler registration**: `forge/telegram_handlers.py` exists but the integration wiring into `handlers.py` main dispatcher was part of S66 Forge MVP — verify this is fully registered.

---

## Open Threads

- Resolve inquiry listener vs. bot polling conflict — options: webhook mode, separate bot token for tender, file-based queue (tender-inbox.jsonl, fully implemented)
- Telegram as notification channel for Wilbur interrupt gradient (Levels 2–3) — this is the intended path per wilbur-vision.md; wiring not yet built
- Idea intake via Telegram currently routes to local `ideas/` repo — the intention was always that approved ideas become lugs; the daily reminder script (`scripts/idea_reminder.py`) + cron are installed but not always active
