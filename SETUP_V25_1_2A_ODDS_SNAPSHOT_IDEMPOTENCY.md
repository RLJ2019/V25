# Setup V25.1.2a — Odds Snapshot Idempotency Hotfix

## Doel van deze hotfix

V25.1.2a is bedoeld als laatste kleine hardening vóór de 5-speeldagen shadow-validatie. De build voorkomt dat bijna-identieke odds snapshots met alleen secondeverschil onnodig als unieke database records worden opgeslagen.

## GitHub upload

Upload de inhoud van deze ZIP naar je GitHub repository en laat de bestaande workflows draaien.

## Verplichte checks vóór shadowfase

Draai minimaal:

```text
python -m compileall football_agent -q
python smoke_test.py
python -m unittest discover -s tests
python -m football_agent.scripts.healthcheck
TELEGRAM_ENABLED=false python run_agent.py
TELEGRAM_ENABLED=false python -m football_agent.scripts.run_lineup_monitor
DATABASE_ENABLED=true DATABASE_SHADOW_MODE=true SHADOW_COMPARE_FAIL_CLOSED=true python -m football_agent.scripts.compare_shadow_state
```

## Aanbevolen GitHub Variables voor shadowfase

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

## Shadowfase criteria

Ga pas naar de volgende build als minimaal 5 speeldagen gelden:

```text
Daily workflow: groen
Line-up monitor: groen
Compare shadow: PASS
critical_errors: 0
shadow_parity_percent: 100.0
Geen explosieve groei in odds_snapshots door duplicate timestamp-seconden
```

## Niet doen in V25.1.2a fase

Nog niet:

```text
TELEGRAM_ENABLED=true
DATABASE_SHADOW_MODE=false
settlement workflow bouwen
The Odds API koppelen
MAX_MATCHES fors verhogen
```

Eerst infrastructuur bewijzen met kleine, gecontroleerde runs.
