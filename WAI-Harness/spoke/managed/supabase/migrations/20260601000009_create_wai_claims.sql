-- Migration: Create wai_claims table for chain claim registry
-- Spec: spec-goal-chain-v1 — distributed session coordination primitive
--
-- An agent claims a chain before planning begins (prevents concurrent session races).
-- Claims expire after ttl_hours; expired claims become investigation lugs (not silent resets).
-- PRIMARY KEY on chain_id ensures only one active claim per chain (DB-enforced atomic claiming).

CREATE TABLE IF NOT EXISTS public.wai_claims (
  chain_id      text PRIMARY KEY,
  session_id    text NOT NULL,
  wheel_id      text NOT NULL,
  claimed_at    timestamptz NOT NULL DEFAULT now(),
  ttl_hours     int NOT NULL DEFAULT 6,
  expires_at    timestamptz GENERATED ALWAYS AS (claimed_at + ttl_hours * interval '1 hour') STORED,
  file_scope    jsonb NOT NULL DEFAULT '[]'::jsonb
);

-- TTL sweep: find expired claims quickly
CREATE INDEX IF NOT EXISTS idx_wai_claims_expires_at
  ON public.wai_claims (expires_at);

-- Per-spoke chain queries
CREATE INDEX IF NOT EXISTS idx_wai_claims_wheel_id
  ON public.wai_claims (wheel_id);

-- Row-level security: service role bypasses; anon key may read only own wheel_id claims
ALTER TABLE public.wai_claims ENABLE ROW LEVEL SECURITY;

CREATE POLICY "claims_service_role_all" ON public.wai_claims
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

COMMENT ON TABLE public.wai_claims IS
  'Active chain claims for multi-Ozi distributed coordination. '
  'One row per claimed chain. PK collision rejects concurrent claims on same chain. '
  'Spec: spec-goal-chain-v1.';

COMMENT ON COLUMN public.wai_claims.chain_id IS 'Foreign key to chain lug id (bytype/chain/).';
COMMENT ON COLUMN public.wai_claims.session_id IS 'Session that holds this claim.';
COMMENT ON COLUMN public.wai_claims.wheel_id IS 'Spoke wheel_id of the claiming session.';
COMMENT ON COLUMN public.wai_claims.ttl_hours IS 'Claim expires at claimed_at + ttl_hours. Default 6.';
COMMENT ON COLUMN public.wai_claims.expires_at IS 'Computed: claimed_at + ttl_hours * interval 1 hour.';
COMMENT ON COLUMN public.wai_claims.file_scope IS 'Files this session will touch — conflict lock for overlapping sessions.';
