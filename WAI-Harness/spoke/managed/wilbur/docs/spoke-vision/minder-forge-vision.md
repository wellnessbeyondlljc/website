# minder-forge — Spoke Vision

**Module:** minder-forge
**Last updated:** 2026-05-25
**Status:** draft (pending Mario review)

---

## Current State

Forge is Minder's Knowledge Enablement Module — a knowledge base for capturing, enriching, organizing, and querying content from URLs, files, and text. It is fully operational as of S66 (epic-minder-forge-mvp-v1 completed).

**What exists today:**
- `src/minder/forge/` — full module:
  - `models.py` — SourceProfile, KnowledgeNode, data models
  - `ingest.py` — URL + text ingest pipeline
  - `node_writer.py` — write_node(), scores src-* refs only
  - `lane.py` — Lane management (knowledge domains)
  - `score_sources.py` — source scoring with asdict serialization
  - `refresh.py` — scan_stale_nodes(), write_refresh_candidates(), fetch_and_refresh_node(), refresh_lane()
  - `digest.py` — generate_lane_digest(), generate_daily_digest(), caching
  - `visualize.py` — wordcloud, graph, source influence, activity charts
  - `normalize.py` — content normalization
  - `query.py` — knowledge base query
  - `reindex.py` — reindex operations
  - `llm.py` — Forge-specific LLM calls
  - `api.py` — internal API layer
  - `config.py` — Forge configuration
  - `github_crawler.py` — GitHub API-based 5-step crawl (metadata + README + tree + key files)
  - `wai_assessor.py` — post-ingest analysis: covers/spoke_opportunities/lane_opportunities; conversation_opener; provider_scope tags; content_type routing (idea|feature|concept|research|note)
  - `review_queue.py` — 4-state review queue (eval-pending → new → reviewed → deprecated); conversation/directive persistence; save_conversation/save_directive/set_status
  - `telegram_handlers.py` — Telegram commands: `/refresh`, `/forge digest`
- `web/routes_forge.py` — 9+ endpoints including: `/forge`, `/forge/api/stats`, `/forge/api/lanes`, `/forge/api/nodes`, `/forge/api/ask`, `/forge/api/ingest`, `/forge/api/review-queue`, `/forge/api/classify`, `/forge/api/conversation`, `/forge/api/deploy-lug`
- `web/templates/forge.html` — 4-section UI: Overview (KB pulse + recent nodes + trending tags), Review (two-pane: queue list + inline conversation), Search (lane sidebar + Ask/Browse/Digest sub-tabs), Sources (feed management)
- `web/static/css/forge.css` — Forge stylesheet
- `WAI-Spoke/advisors/Minder/Forge/config/lanes.json` — 13 lanes with goal fields

**Operational capabilities:**
- URL ingestion → node creation → LLM assessment → review queue entry
- Non-blocking capture queue (background thread fires immediately, badge shows live count)
- GitHub repo crawler (API-based, 5-step)
- Orko conversation per queue item (persistent across reopens, auto-saves)
- Status filter tabs (All/New/Reviewed/Deprecated)
- Structured brief per item (covers/spoke_opportunities/lane_opportunities/goals)
- Deploy-lug route: writes to spoke seed/ingest/
- Folder import modal with AI routing per file (drag-drop, per-file View button, Orko routing summary)
- Lug draft form: spoke selector dropdown (all spokes from registry), approve-then-deploy flow, confirmation badge
- Triage filter tab + Top Picks strip (sorted by spoke-opportunity priority tier)
- 64/64 tests passing (as of S66)

**Data location:** `WAI-Spoke/advisors/Minder/Forge/` — nodes index, lanes, review queue

---

## Intended State

Forge was designed in S66 (session-20260415-1703) as a **knowledge enablement layer** running in parallel to IdeaBank. Key design decisions:

1. **No vectors in Phase 1–3** — explicitly decided; on-demand refresh not automated crawl
2. **Code in src/minder/forge/, data in WAI-Spoke/advisors/Minder/Forge/** — parallel to IdeaBank in MVP
3. **Gemini 2.0-flash for normalization** — with Z.AI fallback
4. **Conversation-first lug drafting** — not deploy-button analysis; full mini-chat to refine before deploying
5. **WAI assessor** — post-ingest analysis surfaces spoke deployment opportunities; "Deploy Lug" is always conversation-mediated
6. **Provider-scope tagging** — `claude_only`/`all_providers`/`note_porting_needed` on each spoke_match so provider-specific implementations are flagged in the UI
7. **Review queue is the central organizing metaphor** — capture flows to queue; queue drives action; nothing gets lost

The longer-term vision (from S116 Wilbur context): Forge feeds PathGraph. Captured knowledge from sessions, URLs, and files becomes structured nodes that Wilbur's Historian can query to understand decision context.

---

## Verified Gap List

- **AI classifier endpoint `/forge/api/classify`** — added in S97; verify it is fully integrated with the folder import modal routing (S97 closeout confirmed this, but cross-check that file-type routing to forge/ideas/tracks is accurate and tested)
- **Lane goals in all 13 lanes** — added in S66 session; verify `WAI-Spoke/advisors/Minder/Forge/config/lanes.json` has goal field on all lanes (session track says "all 13 lanes" but no count verification)
- **GitHub crawler coverage** — currently metadata+README+tree+key files; no issues/PRs/code analysis. Intended for enriching WAI assessment of GitHub repos but limited to public repos and README-level content.
- **Forge as PathGraph seed source** — the design connection between Forge nodes and PathGraph is stated in Wilbur vision but no integration spec exists yet. Forge data is currently self-contained.
- **No Forge tests post-S66** — test suite was 64/64 at S66; subsequent additions (classifier, folder import, conversation persistence) may not have corresponding tests.

---

## Open Threads

- PathGraph integration: Forge nodes should eventually feed Wilbur's Historian; no spec yet for how KnowledgeNode maps to PathGraph entries
- Phase 4+ Forge capabilities (automated crawl, vectors): deliberately deferred but no lug exists to track the deferral timeline
- UAT idea `task-minder-uat-the-behavior-of-the-chat-window-could-be-v1` (ROI 3.0, open) — "Improve Forge Chat Window Behavior"; in work queue, tagged next: false
- Forge's `wai_assessor.py` — assess whether the deploy-lug flow should require a conversation or allow direct deploy for high-confidence assessments; currently conversation is mandatory
