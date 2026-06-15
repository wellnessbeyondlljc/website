-- WAI-Harness v4 storage layer — write discipline (migration 002)
-- spec-storage-layer-v1 write_concurrency + observability workflow tracing.

-- explicit physical state-machine tracing for workflows (causality rests on real rows)
CREATE TABLE IF NOT EXISTS workflow_state_telemetry (
  id               TEXT PRIMARY KEY,
  workflow_id      TEXT NOT NULL,
  step             TEXT NOT NULL,
  status           TEXT CHECK(status IN ('pending','running','done','halted','skipped')),
  actor            TEXT,
  started_at       TEXT,
  ended_at         TEXT,
  span_ms          INTEGER,
  correlation_id   TEXT,
  boundary_context TEXT
);
CREATE INDEX IF NOT EXISTS idx_wst_workflow ON workflow_state_telemetry(workflow_id);

-- daily aggregates produced by retention before pruning raw events (preserves trend signal)
CREATE TABLE IF NOT EXISTS event_daily_summary (
  day        TEXT NOT NULL,
  type       TEXT NOT NULL,
  count      INTEGER NOT NULL,
  aggregated_at TEXT NOT NULL,
  PRIMARY KEY (day, type)
);
