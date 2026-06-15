-- Activity Events: structured telemetry for all session, tool, and model activity
-- Partitioned by month for query performance at scale
-- NOT git-tracked (Postgres-only per WAI principle; queue file is the local buffer)

CREATE TABLE IF NOT EXISTS activity_events (
    id              uuid            DEFAULT gen_random_uuid(),
    ts              timestamptz     NOT NULL,
    wheel_id        text            NOT NULL,
    session_id      text            NOT NULL,
    session_kind    text,
    event_type      text            NOT NULL,
    provider        text,
    model           text,
    tool_name       text,
    work_category   text[],
    duration_ms     int,
    tokens_in       int,
    tokens_out      int,
    cost_estimate_usd numeric(10,6),
    outcome         text,
    lug_refs        text[],
    parent_event_id uuid,
    metadata        jsonb,
    PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);

-- Initial partitions (add more as months arrive)
CREATE TABLE IF NOT EXISTS activity_events_2026_05
    PARTITION OF activity_events
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE IF NOT EXISTS activity_events_2026_06
    PARTITION OF activity_events
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE IF NOT EXISTS activity_events_2026_07
    PARTITION OF activity_events
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

-- Indexes
CREATE INDEX IF NOT EXISTS activity_events_wheel_ts_idx   ON activity_events (wheel_id, ts);
CREATE INDEX IF NOT EXISTS activity_events_session_idx    ON activity_events (session_id);
CREATE INDEX IF NOT EXISTS activity_events_event_type_idx ON activity_events (event_type, ts);
