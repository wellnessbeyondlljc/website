# minder-tracks — Spoke Vision

**Module:** minder-tracks
**Last updated:** 2026-05-25
**Status:** draft (pending Mario review)

---

## Current State

The tracks module is Minder's session track ingestion, storage, and exploration system. It receives WAI session tracks from Claude Code sessions (via Telegram file upload or the WAI track API), indexes them, and provides a web-based explorer.

**What exists today:**
- `tracks/` directory:
  - `incoming/` — 14 files awaiting processing
  - `accepted/` — 2 processed tracks
  - `rejected/` — 4 rejected tracks
  - `index.json` — track index with metadata per track (session_id, file, telegram metadata, provider, model, turn_count, phase_count, storage_ref)
  - `auto_routing_activity.jsonl` — auto-routing log
  - `_chunks/` — chunked track assembly directory
- `web/routes_tracks.py` — routes:
  - GET/PUT `/api/tracks/<filename>/raw` — raw track read/write
  - GET `/api/tracks/library.json` — track library with full metadata
  - GET `/api/tracks/sources` — track sources summary
  - POST `/api/tracks/ingest` — ingest a track file
  - POST `/wai/track` — WAI track API (paste from Claude Code explorer)
  - POST `/wai/track/chunk` — chunked WAI track assembly
  - GET `/api/tracks` — list tracks
  - POST `/api/tracks/<filename>/scan` — scan a track for items
  - GET `/api/tracks/fetch` — fetch from Telegram by file_id
  - GET/PUT `/api/tracks/fs/<path>` — filesystem access
- `web/templates/tracks.html` — Track Vault main listing (New/Accepted/Rejected tabs; ?filter=new auto-selects)
- `web/templates/track_explore.html` — Track Explorer (paste modal, WAI + v0.13 exchange format parsing, multi-line JSON accumulation, decisions/insights/future_task extraction, accordion sidebar)
- `web/track_scanner.py` — track scanning utilities; ^SYSTEM\\s*: with MULTILINE regex; parseLines accumulates multi-line JSON
- `web/routes_tracks_auto_routing.py` — auto-routing logic
- `src/minder/telegram/track_receiver.py` — WAI-CHUNK N/M bot-side reception
- `src/minder/telegram/track_upload.py` — Telegram file upload handling
- `WAI-Spoke/lugs/bytype/feature/completed/feature-minder-track-auto-routing-v1.json` — auto-routing feature completed

**Track format support (Track Explorer):**
- WAI format: event/phase/turn/ts/summary fields
- v0.13 exchange format: p.events[] with decisions/insights/future_task typed events, role/content schema
- ChatGPT export format: turn_index (not turn), timestamp (not ts)
- Multi-provider normalization: track_boundary START fallback for canonical session_id/provider/model

**Parsing edge cases known and handled:**
- Unescaped quotes in string values (tryRepairJson() recursive-descent parser)
- Multi-line JSON objects (parseLines accumulates)
- SYSTEM: pattern false positives (^SYSTEM\\s*: MULTILINE)
- Clipboard JSONL with code examples containing literal quotes

---

## Intended State

From session tracks (S59–S116), the tracks module was designed as the **memory substrate for WAI** — not just a file archive, but the primary source of decisions, intents, and behavioral signals that Wilbur and PathGraph need to read.

Key design intentions:

1. **Tracks are permanent record, not scratch** — every WAI session produces a track; tracks are the authoritative log of what happened, why, and what was decided. Nothing else is as complete.
2. **Multi-format normalization** — tracks arrive from Claude Code, ChatGPT, and other AI environments; the Track Explorer must handle all formats gracefully. This was explicitly hardened in S~85-90 range sessions.
3. **Auto-routing** — incoming tracks should be automatically classified and routed (accepted/rejected/pending) based on content quality signals. `feature-minder-track-auto-routing-v1` is completed.
4. **Scan-to-extract** — each track can be scanned to extract open items (decisions, insights, future tasks) into the Minder library. The `track_scanner.py` + `/api/tracks/<filename>/scan` endpoint enables this.
5. **Chunked upload for long tracks** — the WAI-CHUNK N/M protocol handles tracks too long for a single Telegram message. This is a first-class path, not a workaround.
6. **Track Explorer as review surface** — not just a file viewer; the split-pane with sidebar accordion (decisions/insights/future_tasks) lets Mario extract value from past sessions without re-reading everything.

The long-term vision (from S116 Wilbur doctrine): PathGraph reads session tracks to extract the *spirit* of past decisions — not just the artifact, but the intent. Minder's track module is the intake gateway for PathGraph. Every track Minder ingests becomes a candidate PathGraph node.

---

## Verified Gap List

- **Low acceptance rate**: Only 2 accepted tracks vs 14 incoming + 4 rejected. This suggests the auto-routing criteria may be too strict, or incoming tracks need manual review before auto-routing can work. The nature of the 4 rejected tracks is unknown from available data.
- **PathGraph integration not designed**: Track module stores and indexes tracks but has no connection to a PathGraph consumer. This integration does not exist yet — it's a stated design intent from Wilbur vision but no spec or lug has been written.
- **Telegram track upload → index gap**: Track files arrive via Telegram (file upload or WAI-CHUNK), get stored, and indexed. Verify the `index.json` is always updated atomically — the `storage_ref` field in index.json should link back to the Telegram message for re-fetching if file is lost.
- **Track vault `?filter=new` feature**: Added in S77 — URL param auto-selects New tab. Verify this survived the S511 CSS centralization refactor (inline styles were extracted, JS state should be unaffected but confirm).
- **`_chunks/` directory**: Chunked track assembly staging area. No cleanup mechanism documented — what happens to partial/abandoned chunk assemblies?

---

## Open Threads

- PathGraph integration design: Track Explorer should eventually export decisions/intents as PathGraph entries; no spec exists
- Auto-routing calibration: 14 incoming vs 2 accepted suggests acceptance rate is too low or manual review is needed; no lug tracking this gap
- Cross-session search: Track Vault currently shows per-file views; searching across all tracks for a specific decision or topic is not implemented
- `tracks-viewer-hosting-request-20260320.jsonl` in lugs/inbox — this appears to be an old request from March 2026; check if this is still relevant or can be archived
