# minder-ideas — Spoke Vision

**Module:** minder-ideas
**Last updated:** 2026-05-25
**Status:** draft (pending Mario review)

---

## Current State

The ideas module is Minder's local idea drafting and routing system. Ideas are captured from Telegram or the web, held locally in a draft-to-approval flow, and promoted into Wheelwright lugs when approved.

**What exists today:**
- `ideas/` directory at project root:
  - `ideas.jsonl` — append-only idea drafts (local, not committed to git)
  - `schema.json` — canonical fields: id, title, summary, why_bother, goal, scope, constraints, target, status, source, created_at, updated_at, activity[]
  - `README.md` — workflow documentation
- `ideas/README.md` status flow: `new → draft → approved → delivered`
- `src/minder/ideas_repository.py` — repository class for reading/writing ideas.jsonl
- `src/minder/telegram/idea_intake.py` — IdeaIntakeService; Telegram-side idea intake with why_bother capture and Orko refinement
- `web/app.py` — `/api/ideas`, `/api/ideas/<id>`, `/api/ideas/bulk-create`, `/api/ideas/<id>/send-to-lug` routes
- `web/templates/bulk_intake.html` — bulk idea intake UI
- Orko refinement per-idea: uses existing web detail and Orko flow after creation (decided in S~60)
- Linear status progression: New → Draft → Ready → Delivered (S73: replaced Approve/Decline buttons)
- Deliverable routing UI: spoke selector (hub-registry.json aware, IdeaBank as last fallback), server-side unknown-target → IdeaBank fallback
- `scripts/idea_reminder.py` — daily reminder of open (non-delivered) ideas
- `scripts/install_idea_reminder.sh` — installs cron at 9am daily
- `web/templates/_coo_panel.html` — COO context includes ideas count from `/api/coo/context`
- UAT feedback widget: `routes_feedback.py` + `feedback.html` — separate from ideas module but ideas can trigger UAT submissions

**Known integration points:**
- `web/app.py` provides `count_ideas()` function used in stats endpoint
- Ideas can be delivered to any registered spoke (via hub-registry.json lookup)
- Forge `wai_assessor.py` classifies captured content as `idea` type and routes to ideas module

---

## Intended State

From session tracks (S59–S80, S116), the ideas module had a clear and consistent intent:

1. **Ideas are a staging area, not permanent storage** — they stay local until approved; only approved ideas become outbox lugs. This prevents premature delivery and allows iteration.
2. **why_bother is mandatory** — every idea must have an explicit value/impact statement before it can progress to draft. This was a deliberate quality gate (decided S11).
3. **Bulk intake is extract-then-review-then-create** — not blind persistence from a pasted block (decided S~80); per-idea refinement reuses existing Orko flow after batch creation.
4. **Orko refinement is progressive** — saves as learned, not on approval (fixed after Gemini multi-line JSON bug in S~58). This was a regression that was caught and corrected.
5. **Daily reminder keeps ideas from going stale** — the cron-based reminder was an explicit design decision (S11) to ensure ideas don't disappear into the repo unaddressed.
6. **Inherited target attribution** — for batch intakes, "last explicit target wins" and inferred assignments are marked separately from explicit ones (S~80 decision).
7. **Idea → Lug promotion path** — via `/api/ideas/<id>/send-to-lug`; creates lug in spoke's incoming/ based on spoke registry. The Wheelwright idea intake workflow (hub-registry.json aware routing) was adopted as a formal protocol.

The intended future: ideas feed into Wilbur's TasteGraph as stated preference signals. When Mario captures an idea, the topic, energy level, and recurrence pattern are behavioral signals about what he cares about. This is not yet wired but is the stated intent in wilbur-vision.md.

---

## Verified Gap List

- **IdeaBank vs. ideas/ ambiguity**: Early sessions referenced "IdeaBank" as a spoke target; this was resolved in S60 (deliverable routing UI: IdeaBank is the last fallback in the spoke dropdown). Verify current code uses `ideas/` consistently and "IdeaBank" is only a UI label, not a separate data store.
- **UAT widget is separate from ideas**: The UAT feedback widget (`routes_feedback.py`) scans for `uat-*.json` files in bytype/ — these are not `idea` type objects. The naming and purpose could cause confusion for future agents. Both exist; ideas module ≠ feedback module.
- **Daily reminder cron status**: `scripts/install_idea_reminder.sh` exists, but whether it's active on the current machine is unknown. Cron entries are not part of git. This is a recurring silent-drift risk.
- **Forge-to-ideas routing**: `wai_assessor.py` routes `content_type=idea` captures to the ideas system via the Deploy Lug flow. The exact path (ideas.jsonl vs. web API vs. direct lug) is not verified from session tracks — needs code inspection.
- **ideas.jsonl is gitignored**: Local-only by design but means ideas don't survive machine/repo changes. No backup mechanism documented.

---

## Open Threads

- Wilbur TasteGraph integration: idea topics + recurrence patterns as preference signals — not yet designed; no spec or lug exists
- Idea aging: no mechanism to auto-archive or escalate ideas that have been in `new` status for > N days (beyond the daily reminder script)
- Bulk intake edge cases: the Orko refinement flow for batch creations was designed to reuse per-item detail — verify this works when >10 ideas are created in one batch (pagination, UX at scale)
- Ideas feed into PathGraph? The Wilbur doctrine implies ideas are stated aspirations; PathGraph should track "what Mario said should exist." No integration design exists yet.
