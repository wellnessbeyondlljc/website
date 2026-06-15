-- WAI Fleet Index Schema
-- Migration: 007_hub_advisor_tables
-- Purpose: fleet_priority_overlay table for Prioritizer advisor output
-- Depends on: 001_fleet_index_schema (wheels table must exist)

-- =============================================================================
-- TABLE: fleet_priority_overlay
-- Per-wheel overlay written by Prioritizer advisor after each nightly run.
-- Wakeup protocol reads this to surface fleet-aware next-work recommendations.
-- =============================================================================
CREATE TABLE IF NOT EXISTS fleet_priority_overlay (
    id              TEXT PRIMARY KEY,                   -- e.g. "prioritizer-{wheel_id}-{YYYYMMDD}"
    wheel_id        TEXT NOT NULL REFERENCES wheels(id),
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generated_by    TEXT NOT NULL DEFAULT 'prioritizer',
    recommendations JSONB NOT NULL,                     -- [{lug_id, reason, fleet_context_score, rank}]
    expires_at      TIMESTAMPTZ,                        -- NULL = never expires
    acknowledged_at TIMESTAMPTZ                         -- set when wakeup reads it
);

-- RLS: wheel agents read own overlay; hub service role writes all
ALTER TABLE fleet_priority_overlay ENABLE ROW LEVEL SECURITY;

CREATE POLICY fpo_spoke_read ON fleet_priority_overlay
    FOR SELECT
    USING (wheel_id = current_setting('app.wheel_id', true));

CREATE POLICY fpo_hub_write ON fleet_priority_overlay
    FOR ALL
    USING (current_setting('role', true) = 'service_role');

CREATE INDEX ON fleet_priority_overlay (wheel_id, generated_at DESC);
CREATE INDEX ON fleet_priority_overlay (expires_at) WHERE expires_at IS NOT NULL;
