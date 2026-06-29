-- V25.1.0 Phase 1: Shadow Database Infrastructure
-- Run this once in the Supabase SQL editor. The GitHub agent uses only the
-- server-side secret key; no public/anonymous policies are created.

create extension if not exists pgcrypto;

create table if not exists fixtures (
    fixture_id text primary key,
    api_football_fixture_id bigint,
    football_data_match_id bigint,
    competition_key varchar(100) not null,
    competition_name varchar(150) not null,
    home_team varchar(200) not null,
    away_team varchar(200) not null,
    kickoff_utc timestamptz not null,
    status varchar(40) not null default 'SCHEDULED',
    source varchar(50),
    home_score integer,
    away_score integer,
    updated_at timestamptz not null default now()
);

create table if not exists picks (
    pick_id uuid primary key,
    identity_key text not null unique,
    fixture_id text not null references fixtures(fixture_id) on delete cascade,
    competition_key varchar(100) not null,
    competition_name varchar(150) not null,
    market varchar(50) not null,
    selection varchar(100) not null,
    bookmaker varchar(100),
    status varchar(30) not null,
    advice text,
    entry_odds numeric(10,4),
    fair_odds numeric(10,4),
    sharp_fair_odds numeric(10,4),
    min_acceptable_odds numeric(10,4),
    model_probability numeric(12,8),
    market_probability numeric(12,8),
    expected_value numeric(12,8),
    probability_edge numeric(12,8),
    confidence numeric(5,2),
    data_quality numeric(5,2),
    risk_score numeric(5,2),
    uncertainty_score numeric(5,2),
    stake_units numeric(8,3),
    stake_reason text,
    time_window varchar(30),
    lineup_confirmed boolean not null default false,
    data_snapshot_id text,
    model_version varchar(100),
    config_version varchar(100),
    feature_set_version varchar(100),
    calibration_version varchar(100),
    original_created_at timestamptz,
    last_seen_at timestamptz not null default now()
);

create table if not exists pick_events (
    event_key text primary key,
    event_id bigserial unique,
    pick_id uuid not null references picks(pick_id) on delete cascade,
    event_type varchar(40) not null,
    details jsonb not null default '{}'::jsonb,
    event_timestamp timestamptz not null default now()
);

create table if not exists notification_state_shadow (
    fixture_id text not null,
    market varchar(50) not null,
    selection varchar(100) not null,
    pick_id uuid references picks(pick_id) on delete set null,
    status varchar(30) not null,
    signature text,
    last_action varchar(50),
    message_key varchar(128) unique,
    sent boolean not null default false,
    run_id text,
    last_updated_at timestamptz not null default now(),
    primary key (fixture_id, market, selection)
);

create table if not exists odds_snapshots (
    snapshot_key varchar(128) primary key,
    snapshot_id bigserial unique,
    fixture_id text not null references fixtures(fixture_id) on delete cascade,
    bookmaker varchar(100) not null,
    market varchar(50) not null,
    selection varchar(100) not null,
    odds numeric(10,4) not null,
    profile varchar(30),
    opening_odds numeric(10,4),
    provider_closing_odds numeric(10,4),
    snapshot_timestamp_utc timestamptz not null,
    is_closing_line boolean not null default false,
    captured_at timestamptz not null default now()
);

-- Placeholder table for Phase 3. It is not used as a live source in Phase 1.
create table if not exists settlements (
    settlement_id bigserial primary key,
    pick_id uuid not null unique references picks(pick_id) on delete cascade,
    actual_outcome varchar(100),
    status varchar(30),
    profit_units numeric(10,4),
    stake_returned_units numeric(10,4),
    win_fraction numeric(6,4),
    loss_fraction numeric(6,4),
    closing_odds numeric(10,4),
    clv_odds numeric(12,8),
    clv_probability numeric(12,8),
    settlement_details jsonb not null default '{}'::jsonb,
    settled_at timestamptz
);

create table if not exists workflow_runs (
    run_id text primary key,
    run_type varchar(50) not null,
    source varchar(30),
    status varchar(30) not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    metadata jsonb not null default '{}'::jsonb,
    summary jsonb not null default '{}'::jsonb,
    error text
);

create table if not exists sync_jobs (
    sync_id uuid primary key default gen_random_uuid(),
    run_id text references workflow_runs(run_id) on delete set null,
    sync_type varchar(50) not null,
    status varchar(30) not null,
    details jsonb not null default '{}'::jsonb,
    started_at timestamptz not null default now(),
    finished_at timestamptz
);

create index if not exists idx_fixtures_kickoff on fixtures(kickoff_utc);
create index if not exists idx_picks_fixture on picks(fixture_id);
create index if not exists idx_picks_status on picks(status);
create index if not exists idx_pick_events_pick on pick_events(pick_id, event_timestamp);
create index if not exists idx_odds_fixture_time on odds_snapshots(fixture_id, snapshot_timestamp_utc);
create index if not exists idx_workflow_runs_started on workflow_runs(started_at desc);

alter table fixtures enable row level security;
alter table picks enable row level security;
alter table pick_events enable row level security;
alter table notification_state_shadow enable row level security;
alter table odds_snapshots enable row level security;
alter table settlements enable row level security;
alter table workflow_runs enable row level security;
alter table sync_jobs enable row level security;

-- Intentionally no anon/authenticated policies. Server-side secret/service-role access
-- bypasses RLS. Never expose that secret in a client, artifact, CSV or public sheet.
