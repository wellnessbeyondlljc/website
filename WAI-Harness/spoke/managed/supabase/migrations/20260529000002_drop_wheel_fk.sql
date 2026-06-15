-- Drop FK constraint on activity_events.wheel_id so the emitter can use
-- the spoke's string wheel_id slug (e.g. "wheelwright-framework") directly.
-- The hub can correlate to wheels.id separately if needed.
ALTER TABLE activity_events DROP CONSTRAINT IF EXISTS activity_events_wheel_id_fkey;
