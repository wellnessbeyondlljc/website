-- Migration: 20260529000005_sync_tool_columns
-- Purpose: Add columns expected by index_sync.py to tracks and sessions tables.
-- The remote schema was created independently from the sync tool, so column names
-- diverged. This migration adds the sync-tool-expected columns alongside existing
-- ones. No data is moved — both sets of columns coexist.

-- =============================================================================
-- TABLE: tracks — add columns expected by index_sync.py seed_tracks()
-- Existing: id, wheel_id, session_id, turn, ts, action, thinking, focus,
--           decision_flag, insight_flag, pushback_flag, raw_path, text_embedding
-- sync tool sends: turn_index, event_type, content_summary, lug_ids, model_id
-- =============================================================================

ALTER TABLE tracks
    ADD COLUMN IF NOT EXISTS turn_index     INT,
    ADD COLUMN IF NOT EXISTS event_type     TEXT,
    ADD COLUMN IF NOT EXISTS content_summary TEXT,
    ADD COLUMN IF NOT EXISTS lug_ids        TEXT,
    ADD COLUMN IF NOT EXISTS model_id       TEXT;

-- =============================================================================
-- TABLE: sessions — add columns expected by index_sync.py seed_sessions()
-- Existing: id, wheel_id, started_at, ended_at, session_kind, scenario_fingerprint,
--           outcome_summary, vibe, summary_embedding, completed_lugs, abandoned_lugs
-- sync tool sends: model_id, outcome, turn_count, tokens_used, created_at
-- =============================================================================

ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS model_id     TEXT,
    ADD COLUMN IF NOT EXISTS outcome      TEXT,
    ADD COLUMN IF NOT EXISTS turn_count   INT,
    ADD COLUMN IF NOT EXISTS tokens_used  INT,
    ADD COLUMN IF NOT EXISTS created_at   TIMESTAMPTZ;
