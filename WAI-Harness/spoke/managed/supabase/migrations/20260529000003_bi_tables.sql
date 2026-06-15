-- WAI Fleet Index Schema
-- Migration: 006_bi_tables
-- Purpose: KPI definitions table for the BI (Business Intelligence) layer (Group 8)
-- Depends on: 001_fleet_index_schema (wheels table must exist)

-- =============================================================================
-- TABLE: kpi_definitions
-- Registry of named KPI queries available to dashboard surfaces.
-- BI layer is read-only on the index; writes are handled by the hub service role.
-- =============================================================================
CREATE TABLE IF NOT EXISTS kpi_definitions (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    query               TEXT NOT NULL,
    refresh_cadence     TEXT NOT NULL DEFAULT 'daily',
    scope               TEXT NOT NULL CHECK (scope IN ('wheel', 'team', 'fleet')),
    audience            TEXT NOT NULL CHECK (audience IN ('user', 'team', 'external')),
    active              BOOLEAN NOT NULL DEFAULT true,
    last_viewed_at      TIMESTAMPTZ,
    view_count          INTEGER NOT NULL DEFAULT 0
);

-- Enable RLS — BI index is read-only for all authenticated roles
ALTER TABLE kpi_definitions ENABLE ROW LEVEL SECURITY;

-- All authenticated roles may read KPI definitions
CREATE POLICY kpi_definitions_select_all ON kpi_definitions
    FOR SELECT
    USING (true);

-- Only hub service role can write (handled by Postgres BYPASSRLS)

-- Index for dashboard queries that filter by scope and active state
CREATE INDEX ON kpi_definitions (scope, active);
-- WAI Fleet Index Schema
-- Migration: 006a_initial_kpis
-- Purpose: Seed data for kpi_definitions -- 5 initial fleet health KPIs
-- Depends on: 006_bi_tables (kpi_definitions table must exist)

-- =============================================================================
-- SEED: Initial fleet health KPIs
-- All inserts are idempotent via ON CONFLICT (id) DO NOTHING.
-- =============================================================================

-- KPI 1: Token spend by work category (wheel scope)
INSERT INTO kpi_definitions (id, name, query, refresh_cadence, scope, audience)
VALUES (
    'token_spend_by_category',
    'Token spend by work category (30 days)',
    'SELECT work_category, SUM(tokens_in + tokens_out) AS total_tokens, SUM(cost_estimate_usd) AS total_cost FROM activity_events WHERE wheel_id = :wheel_id AND ts > NOW() - INTERVAL ''30 days'' GROUP BY work_category ORDER BY total_cost DESC',
    'daily',
    'wheel',
    'user'
)
ON CONFLICT (id) DO NOTHING;

-- KPI 2: Session completion rate (wheel scope)
INSERT INTO kpi_definitions (id, name, query, refresh_cadence, scope, audience)
VALUES (
    'session_completion_rate',
    'Session completion rate (30 days)',
    'SELECT COUNT(CASE WHEN outcome = ''success'' THEN 1 END)::float / NULLIF(COUNT(*), 0) AS rate FROM activity_events WHERE wheel_id = :wheel_id AND event_type = ''session_end'' AND ts > NOW() - INTERVAL ''30 days''',
    'daily',
    'wheel',
    'user'
)
ON CONFLICT (id) DO NOTHING;

-- KPI 3: Advisor act rate by advisor (wheel scope)
INSERT INTO kpi_definitions (id, name, query, refresh_cadence, scope, audience)
VALUES (
    'advisor_act_rate',
    'Advisor act rate by advisor (30 days)',
    'SELECT advisor_id, AVG(CASE WHEN user_response = ''acted'' THEN 1.0 ELSE 0.0 END) AS act_rate, COUNT(*) AS n FROM advisor_observations WHERE wheel_id = :wheel_id AND observed_at > NOW() - INTERVAL ''30 days'' GROUP BY advisor_id ORDER BY act_rate DESC',
    'daily',
    'wheel',
    'user'
)
ON CONFLICT (id) DO NOTHING;

-- KPI 4: Teaching adoption rate across fleet (fleet scope)
INSERT INTO kpi_definitions (id, name, query, refresh_cadence, scope, audience)
VALUES (
    'teaching_adoption_rate',
    'Teaching adoption rate across fleet',
    'SELECT COUNT(DISTINCT wheel_id)::float / NULLIF((SELECT COUNT(*) FROM wheels WHERE status = ''active''), 0) AS adoption_rate FROM advisor_registry WHERE advisor_id = :teaching_id',
    'weekly',
    'fleet',
    'team'
)
ON CONFLICT (id) DO NOTHING;

-- KPI 5: Cross-wheel blocker age P95 (fleet scope)
INSERT INTO kpi_definitions (id, name, query, refresh_cadence, scope, audience)
VALUES (
    'cross_wheel_blocker_age_p95',
    'Cross-wheel blocker age P95 (days)',
    'SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM NOW() - created_at) / 86400) AS blocker_age_days_p95 FROM lugs WHERE status = ''blocked''',
    'daily',
    'fleet',
    'team'
)
ON CONFLICT (id) DO NOTHING;
