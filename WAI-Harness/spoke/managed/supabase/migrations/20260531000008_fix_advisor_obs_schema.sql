-- Migration: 008a_fix_advisor_observations_schema
-- Purpose: Align advisor_observations with EvolutionEngine expectations.
--          Migration 008 created the table with a conflicting schema (observation_type
--          CHECK constraint using 'fire'/'miss' values; no fired/user_response/context
--          columns; wheel_id NOT NULL without FK). Migration 005 had the correct schema
--          but was created before 008 and never applied. This migration brings the live
--          table into alignment.
-- Safe to apply: additive only, no data loss. Idempotent (IF NOT EXISTS / IF EXISTS).

-- Add missing columns that EvolutionEngine expects
ALTER TABLE advisor_observations
  ADD COLUMN IF NOT EXISTS fired BOOLEAN,
  ADD COLUMN IF NOT EXISTS user_response TEXT,
  ADD COLUMN IF NOT EXISTS context JSONB;

-- Drop the over-restrictive observation_type check constraint from 008
-- (EvolutionEngine sends 'behavioral' and 'corpus_test', not 'fire'/'miss')
ALTER TABLE advisor_observations
  DROP CONSTRAINT IF EXISTS advisor_observations_observation_type_check;

-- Make wheel_id nullable (EvolutionEngine does not always set it)
ALTER TABLE advisor_observations
  ALTER COLUMN wheel_id DROP NOT NULL;

-- Index for efficient recurrence checking by EvolutionEngine
CREATE INDEX IF NOT EXISTS idx_adv_obs_pattern ON advisor_observations
  (advisor_id, pattern_id, fired) WHERE fired = TRUE;
