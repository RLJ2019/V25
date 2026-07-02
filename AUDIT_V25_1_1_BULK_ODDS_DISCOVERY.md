# Audit V25.1.1 — Bulk Odds Discovery Build

## Doel

V25.1.1 lost de operationele odds-blokkade op die tijdens de live shadowtest zichtbaar werd:

- API-Football Pro-key werkt;
- fixtures worden opgehaald;
- `/odds` wordt aangeroepen;
- er zijn geen 429-fouten of databasefouten;
- maar de agent besteedde `MAX_MATCHES` aan de eerste kwalificatie-wedstrijden zonder odds.

De oplossing is een odds-first selectie: eerst bulk odds ontdekken, daarna pas de analyse-slots vullen.

## Belangrijkste wijzigingen

### 1. Live `FIXTURE_SOURCE` wordt nu gerespecteerd

In V25.1.0 werd live mode altijd `source=auto`, ook als GitHub `FIXTURE_SOURCE=api-football` had.
Dat kon football-data fixtures zonder API-Football fixture-id opleveren, waardoor odds-discovery niet betrouwbaar kon matchen.

V25.1.1 gebruikt in live mode nu ook:

```text
FIXTURE_SOURCE=auto | football-data | api-football
```

### 2. Brede fixture-scan, daarna odds-first selectie

Nieuwe variabelen:

```text
ODDS_DISCOVERY_ENABLED=true
ODDS_DISCOVERY_BULK_ENABLED=true
ODDS_DISCOVERY_DAYS=14
ODDS_DISCOVERY_SCAN_LIMIT=250
ODDS_DISCOVERY_MAX_PAGES=5
ODDS_DISCOVERY_MAX_REQUESTS=80
```

`MAX_MATCHES` blijft het aantal wedstrijden dat uiteindelijk wordt geanalyseerd.
`ODDS_DISCOVERY_SCAN_LIMIT` is de bredere voorselectie waaruit wedstrijden met odds prioriteit krijgen.

### 3. Bulk odds ingestion

Nieuwe logica in `football_agent/data/odds.py`:

- groep fixtures per `league_id + kickoff_date`;
- vraag odds bulk op via API-Football;
- lees paginated pages tot `ODDS_DISCOVERY_MAX_PAGES`;
- stop veilig bij `ODDS_DISCOVERY_MAX_REQUESTS`;
- bouw een index op `api_football_fixture_id`;
- selecteer fixtures met odds eerst.

### 4. Geen fixture-loop odds-spam meer

Wanneer bulk discovery actief is, doet de analyse-loop niet meer per geselecteerde fixture automatisch:

```text
/odds?fixture=ID
```

De analyse gebruikt de vooraf ontdekte odds-index.
Fixtures zonder odds krijgen lege odds en blijven veilig `NO_BET`.

### 5. Nieuwe odds-telemetrie in shadow report

`shadow_database_report.json` krijgt nu `odds_metrics`:

```json
{
  "enabled": true,
  "bulk_enabled": true,
  "discovery_window_days": 14,
  "max_pages_per_query": 5,
  "max_requests": 80,
  "fixtures_scanned_total": 0,
  "fixtures_considered_for_odds": 0,
  "fixtures_skipped_no_api_id": 0,
  "fixtures_skipped_outside_window": 0,
  "bulk_queries": 0,
  "odds_requests": 0,
  "odds_pages_fetched": 0,
  "odds_results_zero": 0,
  "fixtures_with_odds": 0,
  "fixtures_without_odds": 0,
  "odds_rows_discovered": 0,
  "odds_rows_written": 0,
  "odds_provider_errors": 0,
  "selected_with_odds": 0,
  "selected_without_odds": 0,
  "request_limit_reached": false
}
```

Dezelfde odds metrics worden ook meegestuurd in de `workflow_runs.summary`.

## Nieuwe/gewijzigde bestanden

```text
football_agent/data/odds.py
football_agent/data/api_football.py
football_agent/data/fixtures.py
football_agent/scripts/run_daily.py
football_agent/database/models.py
football_agent/database/shadow_writer.py
football_agent/storage/model_versions.py
.env.example
tests/test_v25_1_1_odds_discovery.py
BUILD_MANIFEST_V25_1_1.json
SETUP_V25_1_1_BULK_ODDS_DISCOVERY.md
```

## Validatie

```text
python -m compileall football_agent -q && python smoke_test.py && python -m unittest discover -s tests
73 passed
```

## Verwachte live test

Veilige GitHub variables:

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

Daarna `mode=daily` draaien en controleren:

```text
odds_metrics.odds_requests > 0
odds_metrics.fixtures_considered_for_odds > 0
odds_metrics.fixtures_with_odds >= 0
odds_metrics.odds_results_zero verklaart lege providerdagen
```

Als er odds beschikbaar zijn voor de komende 14 dagen, verwachten we:

```text
odds_rows > 0
odds_metrics.odds_rows_written > 0
selected_with_odds > 0
```

## Bewuste beperkingen

- Dit is nog geen The Odds API-integratie.
- Dit is nog geen canonical provider mapping.
- Database blijft shadow mode.
- Telegram blijft uit tijdens deze validatiefase.
- Bulk discovery schrijft odds voor geselecteerde wedstrijden; geen volledige historische odds warehouse-backfill.
