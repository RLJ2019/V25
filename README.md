# V25 Multi-League Value Prediction Engine

## V25.1.0 Phase 1 — Shadow Database Infrastructure

Deze build voegt een veilige dual-write database-laag toe zonder de bestaande, werkende V25.0.9-pipeline te vervangen.

> Bestaande CSV/JSON + Telegram blijven leidend. Supabase/PostgreSQL draait uitsluitend als shadow mirror totdat parity aantoonbaar 100% is.

## Wat deze build doet

- Optionele server-side Supabase REST-verbinding.
- Fail-open shadow writes: database-uitval breekt de agent, Telegram of artifacts niet.
- Centrale shadow-tabellen voor fixtures, picks, pick-events, notification-state, odds snapshots en workflow-runs.
- Deterministische `pick_id` en `identity_key`, zodat herhaalde runs geen dubbele picks creëren.
- Append-only event ledger via `pick_events`.
- Lokale auditbestanden:
  - `output/shadow_database_report.json`
  - `output/shadow_database_failures.jsonl` bij fouten
  - `output/shadow_parity_report.json`
- Database-healthcheck en shadow-parity scripts.
- Alle vier workflows ondersteunen dezelfde databaseconfiguratie en dezelfde shared cache-prefix tijdens de migratiefase.
- Telegram blijft centraal via `TELEGRAM_ENABLED` aan/uit te zetten.

## Belangrijk

V25.1.0 Phase 1 verandert niet:

- de modelbeslissing;
- de Value Pick-selectie;
- staking;
- Telegram-deduplicatie;
- de line-upmonitor;
- de huidige CSV/JSON-bron van waarheid.

De database is in deze fase nog **niet** leidend.

## Installatie

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m compileall football_agent -q
python smoke_test.py
python -m unittest discover -s tests
```

## Supabase eenmalig instellen

1. Maak een Supabase-project aan.
2. Open de SQL Editor.
3. Voer volledig uit:

```text
football_agent/database/migrations/001_initial_schema.sql
```

4. Maak in GitHub bij **Settings → Secrets and variables → Actions → Secrets** aan:

```text
SUPABASE_URL
SUPABASE_SECRET_KEY
```

De secret/service-role key is uitsluitend server-side. Plaats hem nooit in Git, een artifact, CSV, Google Sheet of frontend.

5. Maak bij **Variables** aan:

```text
DATABASE_ENABLED=true
DATABASE_SHADOW_MODE=true
DATABASE_FAIL_OPEN=true
DATABASE_TIMEOUT_SECONDS=20
DATABASE_MAX_RETRIES=2
DATABASE_BATCH_SIZE=250
SHADOW_COMPARE_SINCE_UTC=
```

Tijdens de eerste installatie mag `DATABASE_ENABLED=false` blijven. De agent blijft dan exact functioneren zoals V25.0.9.

## Database-healthcheck

Lokaal:

```bash
python -m football_agent.scripts.run_database_healthcheck
```

Of handmatig via de daily workflow met mode:

```text
database_healthcheck
```

Verwachte uitkomst:

```text
reachable: true
message: Supabase REST connection OK.
```

## Shadow parity vergelijken

Na enkele runs:

```bash
python -m football_agent.scripts.compare_shadow_state
```

Of kies in de daily workflow:

```text
compare_shadow
```

De vergelijking controleert:

- unieke lokale picks versus databasepicks;
- ontbrekende of onverwachte records;
- dubbele database-identiteiten;
- notification-state status/signature mismatches;
- shadow parity-percentage.

## Acceptatiecriteria vóór Phase 2

De database mag pas leidend worden na minimaal vijf echte speeldagen met:

```text
100% lokale picks aanwezig in database
0 database-duplicaten
0 ontbrekende statuswijzigingen
0 notification-state mismatches
database-uitval breekt geen agentrun
herhaalde runs creëren geen dubbele records
```

## Dagelijkse run

```bash
python run_agent.py
```

## Line-up monitor

```bash
python -m football_agent.scripts.run_lineup_monitor
```

De monitor gebruikt praktisch een T-65 tot T-45 window. GitHub Actions garandeert geen exact T-55-startmoment.

## Heartbeat

```bash
python -m football_agent.scripts.run_heartbeat
```

## Backtest en weight-training

```bash
python -m football_agent.scripts.run_backtest
python -m football_agent.scripts.run_weight_training
```

## Telegrambeleid

- Dagrapport: stil.
- Heartbeat: stil.
- Value Pick: luid.
- Pick gewijzigd/bevestigd: luid.
- Pick ingetrokken: luid.
- Geen eurobedragen; staking wordt in units weergegeven.

## Volgende fasen

```text
Phase 2: database wordt source of truth voor state en notificaties
Phase 3: polymorfe settlement, closing snapshots en dual-metric CLV
Phase 4: wekelijkse Telegramrapportage en volledige Google Sheet-spiegel
```

## Filosofie

Minder picks. Betere picks. Geen schijnzekerheid. Volledig auditeerbaar.

## V25.1.1 — Bulk Odds Discovery

V25.1.1 adds odds-first fixture selection. The agent now scans a wider fixture pool, fetches API-Football odds in bulk per league/date with pagination, builds an odds index by API-Football fixture id, and prioritizes fixtures whose bookmaker markets are already open before spending `MAX_MATCHES` analysis slots.

Recommended validation settings:

```text
MAX_MATCHES=5
DAYS_AHEAD=60
FIXTURE_SOURCE=api-football
TELEGRAM_ENABLED=false
DATABASE_ENABLED=true
DATABASE_SHADOW_MODE=true
DATABASE_FAIL_OPEN=true
ODDS_DISCOVERY_ENABLED=true
ODDS_DISCOVERY_BULK_ENABLED=true
ODDS_DISCOVERY_DAYS=14
ODDS_DISCOVERY_SCAN_LIMIT=250
ODDS_DISCOVERY_MAX_PAGES=5
ODDS_DISCOVERY_MAX_REQUESTS=80
```

See `SETUP_V25_1_1_BULK_ODDS_DISCOVERY.md` for the first live test flow.

## V25.1.2 — Shadow Hardening & Operational Efficiency

V25.1.2 reduces odds API-call overhead and strengthens production validation:

- Bulk odds discovery groups by `league_id + season` instead of `league_id + date`.
- Line-up monitor runs use real-time fixture-level odds instead of the morning bulk odds cache.
- Fractional Kelly staking applies a longshot deflator above decimal odds 4.00.
- `compare_shadow_state` can fail closed with `SHADOW_COMPARE_FAIL_CLOSED=true`.

Recommended shadow-test variables:

```text
DATABASE_ENABLED=true
DATABASE_SHADOW_MODE=true
DATABASE_FAIL_OPEN=true
SHADOW_COMPARE_FAIL_CLOSED=true
TELEGRAM_ENABLED=false
FIXTURE_SOURCE=api-football
MAX_MATCHES=5
DAYS_AHEAD=60
ODDS_DISCOVERY_ENABLED=true
ODDS_DISCOVERY_BULK_ENABLED=true
ODDS_DISCOVERY_DAYS=14
ODDS_DISCOVERY_SCAN_LIMIT=250
ODDS_DISCOVERY_MAX_PAGES=5
ODDS_DISCOVERY_MAX_REQUESTS=80
```

See `SETUP_V25_1_2_SHADOW_HARDENING_OPERATIONAL_EFFICIENCY.md` for the test flow.

## V25.1.2a — Odds Snapshot Idempotency Hotfix

V25.1.2a is a small database-hardening release on top of V25.1.2:

- odds snapshot keys normalize provider timestamps to UTC minute precision;
- raw provider timestamps are still stored in `snapshot_timestamp_utc`;
- same bookmaker/market/selection/odds within the same minute deduplicates to one snapshot key;
- true odds moves still create separate snapshot keys because odds remain part of the hash;
- duplicate snapshot keys are deduplicated before Supabase upsert.

This release intentionally keeps the prediction/model versions unchanged because it does not alter the model, pick selection, staking or line-up monitor logic.

See `SETUP_V25_1_2A_ODDS_SNAPSHOT_IDEMPOTENCY.md` for the shadow-test flow.
