-- Drop restrictive check constraints on activity_events so all valid values can be inserted.
-- The event_type_check and outcome_check were created with a limited enum in a prior session.
-- We want open text columns, not constrained enums, to allow future event types.
ALTER TABLE activity_events DROP CONSTRAINT IF EXISTS activity_events_event_type_check;
ALTER TABLE activity_events DROP CONSTRAINT IF EXISTS activity_events_outcome_check;

-- Add columns that may be missing from the initial table creation
ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS provider text;
ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS model text;
ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS tool_name text;
ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS work_category text[];
ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS tokens_in int;
ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS tokens_out int;
ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS cost_estimate_usd numeric(10,6);
ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS parent_event_id uuid;
ALTER TABLE activity_events ADD COLUMN IF NOT EXISTS metadata jsonb;
