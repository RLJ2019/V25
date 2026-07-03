-- V25.1.3 Settlement Pipeline Hardening
-- Adds audit, CLV and policy fields to the existing public.settlements table.
-- IMPORTANT:
--   Build/use this on dev/v25.1.3-settlement-pipeline first.
--   Do NOT run this on the live/main Supabase project until V25.1.2d has completed 5/5 valid shadow days.
--   Existing table design is preserved: settlement_id remains bigint PK, pick_id remains UNIQUE.

alter table public.settlements
  add column if not exists fixture_id text,
  add column if not exists kickoff_utc timestamp with time zone,
  add column if not exists fixture_status text,
  add column if not exists final_score_home integer,
  add column if not exists final_score_away integer,
  add column if not exists score_source text,

  add column if not exists market text,
  add column if not exists selection text,
  add column if not exists line numeric,

  add column if not exists stake_units numeric,
  add column if not exists entry_odds numeric,
  add column if not exists model_probability numeric,
  add column if not exists market_probability numeric,

  add column if not exists closing_bookmaker text,
  add column if not exists closing_snapshot_id text,
  add column if not exists overround numeric,

  add column if not exists clv_market_movement numeric,
  add column if not exists clv_model_vs_close numeric,
  add column if not exists clv_method text,
  add column if not exists clv_warning text,

  add column if not exists settlement_basis text,
  add column if not exists settlement_policy_version text,

  add column if not exists created_at_utc timestamp with time zone default now(),
  add column if not exists updated_at_utc timestamp with time zone default now();

-- Existing constraints observed before V25.1.3:
--   settlements_pkey on settlement_id
--   settlements_pick_id_fkey on pick_id
--   settlements_pick_id_key UNIQUE(pick_id)
-- Therefore, do not recreate the unique constraint unless your environment is missing it.

create index if not exists idx_settlements_pick_id
  on public.settlements (pick_id);

create index if not exists idx_settlements_fixture_id
  on public.settlements (fixture_id);

create index if not exists idx_settlements_settled_at
  on public.settlements (settled_at);

create index if not exists idx_settlements_status
  on public.settlements (status);

create index if not exists idx_settlements_policy_version
  on public.settlements (settlement_policy_version);

create index if not exists idx_settlements_clv_method
  on public.settlements (clv_method);

-- Keep Supabase/PostgREST schema cache fresh after migration.
notify pgrst, 'reload schema';
