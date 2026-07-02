# Setup V25.1.1 — Bulk Odds Discovery

## GitHub Variables

Laat de bestaande database-shadow instellingen staan:

```text
DATABASE_ENABLED=true
DATABASE_SHADOW_MODE=true
DATABASE_FAIL_OPEN=true
DATABASE_TIMEOUT_SECONDS=20
DATABASE_MAX_RETRIES=2
DATABASE_BATCH_SIZE=250
TELEGRAM_ENABLED=false
```

Zet of voeg toe:

```text
FIXTURE_TEST_MODE=false
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

## Waarom twee vensters?

```text
DAYS_AHEAD=60
```

Dit laat de agent breed wedstrijden vinden.

```text
ODDS_DISCOVERY_DAYS=14
```

Dit voorkomt odds-calls voor wedstrijden die te ver in de toekomst liggen en meestal nog geen bookmaker-markt hebben.

## Eerste run

GitHub → Actions → Daily V25 Multi-League Agent → Run workflow

```text
run mode = daily
use historical/test fixtures = false
historical start date = leeg
historical end date = leeg
fixture season = leeg
fixture source = api-football
```

Download daarna `shadow_database_report.json`.

## Wat controleren?

In het rapport:

```text
fixture_rows
odds_rows
pick_rows
failures
odds_metrics
```

Belangrijkste nieuwe velden:

```text
odds_metrics.odds_requests
odds_metrics.odds_results_zero
odds_metrics.fixtures_considered_for_odds
odds_metrics.fixtures_with_odds
odds_metrics.odds_rows_written
odds_metrics.selected_with_odds
```

## Daarna

Draai pas na een goede daily-run:

```text
run mode = compare_shadow
```

Doel:

```text
status = PASS
shadow_parity_percent = 100.0
```
