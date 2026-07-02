# Audit V25.0.3 — Backtest & Data Integrity Engine

## Doel
Deze release voegt de professionele aanbevelingen toe die nodig zijn om de agent meetbaar betrouwbaarder te maken: backtesting, data-audittrail, odds-freshness, tijdvensters, line-up guardrails, onzekerheidsmarges en exposure management.

## Nieuwe functionaliteit

### 1. Backtest-engine
Bestand: `football_agent/scripts/run_backtest.py`

- Accepteert historische CSV-input via `BACKTEST_INPUT`.
- Meet ROI, gemiddelde Brier, binaire log-loss, gemiddelde CLV en positieve CLV-rate.
- Geeft calibration buckets terug op basis van model probability.
- Blokkeert lookahead-bias niet automatisch, maar documenteert expliciet dat input alleen pre-match beschikbare data mag bevatten.

### 2. Data snapshot audit trail
Bestand: `football_agent/storage/data_snapshots.py`

- Per fixture wordt een JSON-snapshot opgeslagen.
- Snapshot bevat fixture, odds, market probabilities, standings, lineups, time window, model/config/feature/calibration versions.
- Er wordt ook een `data_snapshots_index.csv` aangemaakt.
- Elke prediction logregel krijgt een `data_snapshot_id`.

### 3. Odds freshness / CLV-voorbereiding
Bestand: `football_agent/storage/odds_timeline.py`

- Controleert de nieuwste odds timestamp.
- Geeft terug of odds vers genoeg zijn voor een officiële Value Pick.
- Bereidt de infrastructuur voor om closing odds en CLV structureel te beoordelen.

### 4. Time-window scans
Bestand: `football_agent/utils_time.py`

- Classificeert wedstrijden als `FUTURE`, `EARLY`, `PREMATCH`, `FINAL` of `LIVE_OR_CLOSED`.
- Deze tijdvensters worden gelogd en gebruikt in onzekerheidsberekening en line-up guardrails.

### 5. Line-up confirmation mode
Bestanden: `football_agent/scripts/run_daily.py`, `football_agent/decision/no_bet_rules.py`

- Bij `FINAL` probeert de agent line-ups op te halen via API-Football.
- Indien `REQUIRE_FINAL_LINEUP_FOR_VALUE_PICK=true`, wordt een Value Pick in final scan geblokkeerd zonder bevestigde line-ups.

### 6. Probability uncertainty ranges
Bestand: `football_agent/models/uncertainty_model.py`

- Berekent per selectie een kansrange.
- Onzekerheid wordt groter bij lage datakwaliteit, lage confidence, oude odds, market fallback of ontbreken van line-ups in final scan.
- PickSelector logt de kansrange van de gekozen selectie.
- NoBetRules blokkeert picks als de marktprobability binnen de onzekerheidsmarge valt.

### 7. Exposure/risk management
Bestand: `football_agent/decision/exposure_manager.py`

- Voorkomt te veel gecorreleerde Value Picks.
- Limieten per competitie, team en fixture.
- Overtollige Value Picks worden gedowngraded naar Watchlist.

### 8. Prediction logging uitgebreid
Bestand: `football_agent/storage/prediction_log.py`

Nieuwe velden:

- `uncertainty_score`
- `probability_interval_low`
- `probability_interval_high`
- `time_window`
- `lineup_confirmed`
- `data_snapshot_id`
- `model_version`
- `config_version`
- `feature_set_version`
- `calibration_version`

## Testresultaten

Uitgevoerd op 19 juni 2026:

```bash
python smoke_test.py
python -m unittest discover -s tests
python -m compileall football_agent -q
python -m football_agent.scripts.healthcheck
TELEGRAM_ENABLED=false LOCAL_OUTPUT_DIR=/mnt/data/v25_0_3_run_output python run_agent.py
LOCAL_OUTPUT_DIR=/mnt/data/v25_0_3_run_output python -m football_agent.scripts.run_backtest
```

Resultaat:

- Smoke test: OK
- Unit tests: 24 tests OK
- Compile check: OK
- Healthcheck: OK
- Daily run zonder API-keys crasht niet
- Backtest script zonder input geeft correcte instructie-output

## Professioneel oordeel
V25.0.3 maakt de agent niet per se direct agressiever in picks. Integendeel: hij wordt strenger. Dat is bewust. De grootste verbetering zit in meetbaarheid en controleerbaarheid: elke voorspelling is terug te leiden naar een data snapshot, tijdvenster, odds freshness en modelversie. Dit is essentieel om later met historische data en CLV te bepalen of de agent werkelijk sterker wordt.

## Bekende beperkingen

1. Backtesting is afhankelijk van aangeleverde historische odds/resultaten.
2. Line-up confirmation werkt alleen als API-Football lineups beschikbaar zijn.
3. Uncertainty ranges zijn conservatieve guardrails, nog geen volledig Bayesian posterior model.
4. Exposure management is portfolio-logica, geen kansmodel.
5. Extra markten zoals O/U, BTTS, DNB en Asian Handicap zijn nog niet volledig live geïntegreerd.

## Aanbevolen volgende stap
V25.0.4 zou zich moeten richten op structurele odds-timeline verzameling met meerdere snapshots per wedstrijd en echte closing odds, zodat CLV niet alleen achteraf kan worden gemeten maar actief onderdeel wordt van de beslislogica.
