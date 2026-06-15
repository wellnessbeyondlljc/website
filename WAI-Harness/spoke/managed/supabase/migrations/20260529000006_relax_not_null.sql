-- Migration: 20260529000006_relax_not_null
-- Purpose: The index_sync.py tool sends turn_index (not turn) for tracks rows.
-- The turn column is NOT NULL but sync tool doesn't populate it.
-- Relax NOT NULL on legacy columns that index_sync doesn't populate.

ALTER TABLE tracks ALTER COLUMN turn DROP NOT NULL;
