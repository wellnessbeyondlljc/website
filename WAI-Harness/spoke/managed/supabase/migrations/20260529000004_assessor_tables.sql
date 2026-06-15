-- WAI Fleet Index Schema
-- Migration: 004_assessor_tables
-- Purpose: Assessor advisor recommendations table (Group 5)
-- Depends on: 001_fleet_index_schema (wheels table), 003_activity_events (data source)
-- NOTE: The Assessor advisor must NOT be piloted until >= 200 activity_events rows
--       exist across >= 3 work_categories AND >= 30 days of data have accumulated.
--       This constraint is enforced in the advisor pilot_contract, not this schema.

-- =============================================================================
-- TABLE: assessor_recommendations
-- Fleet-wide model/provider recommendations per work category.
-- Populated by the Assessor advisor from activity_events aggregates.
-- NOT wheel-specific — recommendations are fleet-wide signals derived by the hub.
-- Spoke agents have read-only access; hub service role writes.
-- =============================================================================
CREATE TABLE IF NOT EXISTS assessor_recommendations (
    work_category             TEXT NOT NULL,
    provider                  TEXT NOT NULL,              -- anthropic | openai | google | local
    model                     TEXT NOT NULL,              -- e.g. claude-sonnet-4-6
    tool_set                  TEXT[],                     -- optional tool configuration used
    observed_n                INT NOT NULL DEFAULT 0,     -- sample size (number of events)
    observed_success_rate     NUMERIC(4,3),               -- 0.000 to 1.000
    observed_avg_duration_ms  INT,                        -- average duration across observed events
    observed_avg_cost_usd     NUMERIC(10,6),              -- average cost per event
    confidence                TEXT NOT NULL CHECK (confidence IN ('unrated', 'low', 'medium', 'high')),
    -- Confidence level semantics:
    --   'unrated' = no observations yet for this (work_category, provider, model) combination.
    --               This is NOT the same as 'low'. A new model with no data is unrated,
    --               not unrecommended. Surface as "unrated" at display time, never as low-confidence.
    --   'low'     = some observations exist but insufficient to trust the recommendation.
    --               Sample size present but below confidence threshold.
    --   'medium'  = moderate confidence; decent sample size with reasonable consistency.
    --   'high'    = high confidence; large, consistent sample across the observation window.
    last_updated              TIMESTAMPTZ DEFAULT NOW(),
    sample_window_start       TIMESTAMPTZ,               -- start of the rolling observation window
    sample_window_end         TIMESTAMPTZ,               -- end of the rolling observation window
    PRIMARY KEY (work_category, provider, model)
);

-- =============================================================================
-- ROW LEVEL SECURITY: fleet-wide table; not wheel-scoped.
-- Spoke agents: read-only (recommendations are authoritative fleet signals).
-- Hub writes use service role which bypasses RLS; no explicit hub write policy needed.
-- =============================================================================
ALTER TABLE assessor_recommendations ENABLE ROW LEVEL SECURITY;

-- Spoke agents: read-only access (recommendations are fleet-wide, not wheel-specific)
CREATE POLICY assessor_recommendations_spoke_read ON assessor_recommendations
    FOR SELECT
    USING (true);  -- any authenticated client can read

-- Hub write policy: hub service role bypasses RLS for INSERT/UPDATE/DELETE
-- No explicit hub policy needed when using Supabase service role key

-- =============================================================================
-- INDEXES
-- =============================================================================

-- Primary query pattern: filter by category, then sort/filter by confidence
CREATE INDEX ON assessor_recommendations (work_category, confidence);

-- Freshness queries: find stale recommendations for re-evaluation
CREATE INDEX ON assessor_recommendations (last_updated DESC);
