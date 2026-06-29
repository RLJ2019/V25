# Setup V25.1.2 — Shadow Hardening & Operational Efficiency

## Aanbevolen Variables voor eerste test

```text
MAX_MATCHES=5
DAYS_AHEAD=60
FIXTURE_SOURCE=api-football
TELEGRAM_ENABLED=false
DATABASE_ENABLED=true
DATABASE_SHADOW_MODE=true
DATABASE_FAIL_OPEN=true
SHADOW_COMPARE_FAIL_CLOSED=true
ODDS_DISCOVERY_ENABLED=true
ODDS_DISCOVERY_BULK_ENABLED=true
ODDS_DISCOVERY_DAYS=14
ODDS_DISCOVERY_SCAN_LIMIT=250
ODDS_DISCOVERY_MAX_PAGES=5
ODDS_DISCOVERY_MAX_REQUESTS=80
```

## Test 1 — daily run

GitHub:

```text
Actions → Daily V25 Multi-League Agent → Run workflow
mode = daily
fixture source = api-football
```

Controleer artifact:

```text
shadow_database_report.json
```

Belangrijkste velden:

```text
fixture_rows
odds_rows
pick_rows
failures
odds_metrics.bulk_queries
odds_metrics.odds_requests
odds_metrics.fixtures_with_odds
odds_metrics.odds_rows_written
```

## Test 2 — compare shadow

Daarna draaien:

```text
mode = compare_shadow
```

Bij succes:

```text
status = PASS
critical_errors = 0
shadow_parity_percent = 100.0
```

Bij fout:

```text
status = FAIL
critical_errors > 0
```

Met `SHADOW_COMPARE_FAIL_CLOSED=true` wordt GitHub dan rood. Dat is gewenst gedrag voor V25.1.2.

## Belangrijk voor line-up monitor

De line-up monitor forceert bulk-discovery automatisch uit. Dit is bewust:

```text
ONLY_LINEUP_WINDOW=true
of AGENT_RUN_TYPE=lineup_monitor
→ realtime fixture odds fallback
```

Zo gebruikt de T-55 monitor actuele closing-line odds in plaats van oude discovery-cache.

## Niet doen in deze fase

Nog niet:

```text
TELEGRAM_ENABLED=true
DATABASE_SHADOW_MODE=false
MAX_MATCHES heel hoog zetten
The Odds API integreren
```

Eerst bevestigen:

```text
daily run werkt
compare_shadow PASS
geen API-call explosie
odds_metrics logisch
```
