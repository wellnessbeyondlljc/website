-- WAI-Harness v4 storage layer — initial schema (migration 001)
-- spec-storage-layer-v1. Idempotent (IF NOT EXISTS). FTS5 baseline; vector tables added by the create script if sqlite-vec loads.

-- migration bookkeeping
CREATE TABLE IF NOT EXISTS schema_migrations (
  version    TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

-- WHO: sessions
CREATE TABLE IF NOT EXISTS sessions (
  id              TEXT PRIMARY KEY,
  started_at      TEXT NOT NULL,
  ended_at        TEXT,
  model           TEXT,
  tokens_in       INTEGER,
  tokens_out      INTEGER,
  lugs_touched    TEXT,   -- JSON array
  advisor_reports TEXT    -- JSON
);

-- JOIN / fingerprint: bolts (opened at session start; status updated at pattern close)
CREATE TABLE IF NOT EXISTS bolts (
  id         TEXT PRIMARY KEY,
  session_id TEXT REFERENCES sessions(id),
  certifier  TEXT NOT NULL,
  status     TEXT CHECK(status IN ('open','in_progress','pass','needs_review')),
  opened_at  TEXT NOT NULL,
  closed_at  TEXT
);

CREATE TABLE IF NOT EXISTS bolt_patterns (
  bolt_id    TEXT REFERENCES bolts(id),
  pattern_id TEXT REFERENCES patterns(id),
  PRIMARY KEY (bolt_id, pattern_id)
);

-- 3rd-party certification: patterns
CREATE TABLE IF NOT EXISTS patterns (
  id          TEXT PRIMARY KEY,
  flow_id     TEXT NOT NULL,
  step_id     TEXT NOT NULL,
  session_id  TEXT REFERENCES sessions(id),
  attempt     INTEGER NOT NULL DEFAULT 1,
  disposition TEXT CHECK(disposition IN ('approved','halted','escalate')),
  evidence_path TEXT,
  file_paths  TEXT,   -- JSON array
  created_at  TEXT NOT NULL
);

-- atomic assertion: checks (result 0=loose/uncertified, 1=tight/bolt-verified)
CREATE TABLE IF NOT EXISTS checks (
  id         TEXT PRIMARY KEY,
  pattern_id TEXT REFERENCES patterns(id),
  check_name TEXT NOT NULL,
  criterion  TEXT NOT NULL,
  observed   TEXT,
  result     INTEGER CHECK(result IN (0,1)),
  bolt_id    TEXT REFERENCES bolts(id)
);

-- cross-session gate aggregate (denormalized; mirrors gate-log.jsonl)
CREATE TABLE IF NOT EXISTS gate_log (
  id          TEXT PRIMARY KEY,
  flow_id     TEXT NOT NULL,
  step_id     TEXT NOT NULL,
  session_id  TEXT REFERENCES sessions(id),
  attempt     INTEGER NOT NULL,
  disposition TEXT CHECK(disposition IN ('approved','halted','escalate')),
  evidence    TEXT,
  refinement  TEXT,
  created_at  TEXT NOT NULL
);

-- the unified event bus (indexed view over the JSONL journal)
CREATE TABLE IF NOT EXISTS events (
  event_id       TEXT PRIMARY KEY,
  ts             TEXT NOT NULL,
  spoke          TEXT,
  session        TEXT,
  actor          TEXT,
  type           TEXT NOT NULL,
  subject_ref    TEXT,
  status         TEXT,
  evidence       TEXT,
  correlation_id TEXT,
  parent_event   TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);

-- CapabilitiesGraph entries
CREATE TABLE IF NOT EXISTS cg_entries (
  id            TEXT PRIMARY KEY,
  situation     TEXT NOT NULL,
  solution      TEXT NOT NULL,
  tier          TEXT CHECK(tier IN ('mandated','recommended','awareness')),
  owner_advisor TEXT,
  file_paths    TEXT,  -- JSON
  symbol_refs   TEXT,  -- JSON
  source        TEXT CHECK(source IN ('hub','group','local')),
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

-- PathGraph entries (narrative trajectory)
CREATE TABLE IF NOT EXISTS pg_entries (
  id           TEXT PRIMARY KEY,
  object_type  TEXT CHECK(object_type IN ('lug','initiative')),
  object_id    TEXT NOT NULL,
  status       TEXT NOT NULL,
  title        TEXT NOT NULL,
  initiative_id TEXT,
  created_at   TEXT NOT NULL,
  completed_at TEXT
);

-- TasteGraph profiles
CREATE TABLE IF NOT EXISTS tg_profiles (
  id          TEXT PRIMARY KEY,
  party       TEXT NOT NULL UNIQUE,
  preferences TEXT,  -- JSON
  updated_at  TEXT NOT NULL
);

-- test results (version-stamped history)
CREATE TABLE IF NOT EXISTS test_results (
  id         TEXT PRIMARY KEY,
  test_id    TEXT NOT NULL,
  owner_type TEXT CHECK(owner_type IN ('lug','flow','advisor')),
  owner_id   TEXT NOT NULL,
  result     TEXT CHECK(result IN ('pass','fail')),
  run_at     TEXT NOT NULL,
  version    TEXT,
  output     TEXT
);

-- GitNexus bridge
CREATE TABLE IF NOT EXISTS gitnexus_refs (
  id            TEXT PRIMARY KEY,
  object_type   TEXT CHECK(object_type IN ('check','cg_entry','pattern')),
  object_id     TEXT NOT NULL,
  symbol        TEXT NOT NULL,
  ref_type      TEXT CHECK(ref_type IN ('impacts','owns','tests','fails_in')),
  impact_radius TEXT  -- JSON cache
);

-- FTS5 baseline (always-on search; vector search is the enhancement layer)
CREATE VIRTUAL TABLE IF NOT EXISTS cg_fts USING fts5(id UNINDEXED, situation, solution);
CREATE VIRTUAL TABLE IF NOT EXISTS pattern_fts USING fts5(id UNINDEXED, evidence);
CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5(id UNINDEXED, summary);
