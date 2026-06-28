# Audit V25.0.4 Optimization & Accuracy Upgrade

## Doel

Deze versie verwerkt de nieuwste professionele aanbevelingen uit de V25.0.3 audit. De nadruk ligt niet op meer voetbalpraat, maar op betere inputweging, marktdiscipline en robuuste onzekerheidsmeting.

## Toegevoegde upgrades

### 1. Trainbare overlay-gewichten

Nieuwe module: `football_agent/models/weighting.py`

- Defaultgedrag blijft gelijk aan V25.0.3.
- `football_agent/config/learned_model_weights.json` kan per competitie conservatieve multipliers bevatten.
- `python -m football_agent.scripts.run_weight_training` kan op basis van historische prediction logs bounded multipliers genereren.
- Multipliers zijn bewust begrensd om overfitting te voorkomen.

### 2. Exponential time-decay in xG

Gewijzigd: `football_agent/models/xg_model.py`

- Nieuwe dataclass `TeamMatchPerformance`.
- Recente wedstrijden wegen zwaarder dan oudere wedstrijden.
- Legacy last-5 aggregate velden blijven ondersteund.

### 3. Active CLV / sharp movement guardrail

Gewijzigd: `football_agent/storage/odds_timeline.py`, `decision/no_bet_rules.py`, `scripts/run_daily.py`

- Sharp implied probability movement wordt berekend uit opening odds versus current odds.
- Positieve beweging betekent dat de scherpe markt de selectie steunt.
- Negatieve beweging tegen de selectie blokkeert officiële Value Picks.

### 4. Bootstrapped uncertainty

Gewijzigd: `football_agent/models/uncertainty_model.py`

- Als feature-attributie beschikbaar is, worden onzekerheidsintervallen via deterministic Monte Carlo opgebouwd.
- Bij zwakke data worden featurebijdragen ruimer geperturbeerd.
- Rule-based fallback blijft aanwezig.

### 5. Extra value-markten

Gewijzigd: `data/api_football.py`, `data/odds.py`, `models/value_engine.py`, `scripts/run_daily.py`

- Naast 1X2 worden nu ook `OVER_UNDER_2_5` en `BTTS` ondersteund.
- Poisson-output wordt gebruikt voor Over/Under 2.5 en BTTS modelkansen.
- Market cleansing wordt per extra markt apart uitgevoerd.

## Testresultaten

Uitgevoerd:

```bash
python smoke_test.py
python -m unittest discover -s tests
python -m compileall football_agent -q
python -m football_agent.scripts.healthcheck
TELEGRAM_ENABLED=false LOCAL_OUTPUT_DIR=/mnt/data/v25_0_4_run_output python run_agent.py
python -m football_agent.scripts.run_backtest
python -m football_agent.scripts.run_weight_training
```

Resultaat:

- Smoke test OK
- 30 unit tests OK
- Compile check OK
- Healthcheck OK
- Daily run zonder API-keys crasht niet
- Backtest-script geeft correcte instructie-output zonder inputdata
- Weight-training-script crasht niet en schrijft output

## Professioneel oordeel

V25.0.4 is een duidelijke accuratesse-upgrade boven V25.0.3. De belangrijkste stap is dat de agent nu niet alleen sterker rekent, maar ook beter omgaat met:

- recentheid van vormdata;
- beweging van de scherpe markt;
- onzekerheid rond featurebijdragen;
- bredere value-markten;
- toekomstige empirische gewichten per competitie.

De agent blijft bewust defensief. Zonder goede odds, verse data of voldoende edge wordt een wedstrijd geen Value Pick.
