# V25.1.2 — Shadow Hardening & Operational Efficiency

## Build doel

V25.1.2 bouwt verder op V25.1.1 Bulk Odds Discovery. Deze release verlaagt onnodige API-Football odds-calls, forceert actuele odds bij de line-up monitor, dempt longshot-staking en maakt de shadow-vergelijking streng genoeg voor productievalidatie.

## Wijzigingen

### 1. Bulk odds discovery per league/season

Bestanden:

- `football_agent/data/odds.py`
- `football_agent/data/api_football.py`

Aanpassing:

- V25.1.1 groepeerde odds-discovery per `(league_id, kickoff_date)`.
- V25.1.2 groepeert per `league_id` en vraagt odds op via `league + season`.
- De lokale fixture-window blijft bestaan voor candidate filtering.
- Pagination guards blijven actief:
  - `ODDS_DISCOVERY_MAX_PAGES`
  - `ODDS_DISCOVERY_MAX_REQUESTS`

Effect:

- Minder losse API-calls per competitie/weekend.
- Zelfde odds-first selectieprincipe blijft behouden.

### 2. Real-time odds fallback voor line-up monitor

Bestand:

- `football_agent/scripts/run_daily.py`

Aanpassing:

- Als `ONLY_LINEUP_WINDOW=true` of `AGENT_RUN_TYPE=lineup_monitor/lineup-monitor`, wordt bulk odds discovery runtime uitgezet.
- De analyse-loop gebruikt dan automatisch de individuele `api_football.odds(fixture_id)` call.

Effect:

- T-65 tot T-45 minuten monitor gebruikt actuele closing-line odds in plaats van ochtendcache.

### 3. Odds-afhankelijke Kelly-deflator

Bestand:

- `football_agent/decision/staking.py`

Aanpassing:

- Voor decimal odds boven 4.00 wordt de fractional Kelly vóór unit clamp vermenigvuldigd met `4.0 / decimal_odds`.
- Odds 8.00 krijgt dus 0.50x Kelly-risico.

Effect:

- Minder agressieve staking op extreme underdogs.
- Lagere bankroll-variantie en drawdown-risico.

### 4. Fail-closed shadow compare

Bestanden:

- `football_agent/scripts/compare_shadow_state.py`
- `football_agent/database/repository.py`
- `.github/workflows/*.yml`

Aanpassing:

- `compare_shadow_state` controleert nu ook onverwachte database records, missing state, unexpected state en numerieke afwijkingen.
- Numerieke tolerantie: `0.0001`.
- Bij kritieke fouten wordt status `FAIL`.
- Met `SHADOW_COMPARE_FAIL_CLOSED=true` eindigt het script met `sys.exit(1)`.

Gecontroleerde numerieke velden:

- `entry_odds` tegenover lokale `odds`
- `model_probability` tegenover lokale modelkans van de selectie
- `market_probability` tegenover lokale marktkans van de selectie
- `expected_value`
- `probability_edge`
- `stake_units`

## Nieuwe/gewijzigde environment variable

```text
SHADOW_COMPARE_FAIL_CLOSED=true
```

## Tests

Uitgevoerd lokaal:

```text
python -m compileall football_agent -q
python smoke_test.py
python -m unittest discover -s tests
```

Resultaat:

```text
77 tests passed
```

## Nieuwe testmodule

```text
tests/test_v25_1_2_shadow_hardening_efficiency.py
```

Testdekking:

- odds discovery groepeert op league in plaats van date
- line-up monitor runtime detectie
- longshot Kelly-deflator
- fail-closed numeric mismatch detectie
