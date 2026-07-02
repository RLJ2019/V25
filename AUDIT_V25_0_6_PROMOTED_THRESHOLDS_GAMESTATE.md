# AUDIT V25.0.6 - Promoted, Thresholds & Game-State Upgrade

## Doel
Deze versie verwerkt de V25.0.5-auditpunten rond early-season promoted-team bias, universele value thresholds en raw xG-vervuiling door game-state.

## Geïmplementeerde upgrades

### 1. Bayesian Promovendi Elo-Smoothing
Bestanden:
- `football_agent/models/elo_model.py`
- `football_agent/schemas.py`
- `football_agent/scripts/run_daily.py`
- `football_agent/config/competitions.yml`

Promovendi starten niet meer automatisch op de neutrale `default_elo=1500`. Als een team in de competitie-config als promoted staat en nog geen live rating heeft, gebruikt het model `promoted_elo=1435`. Zodra het Elo-model echte wedstrijddata heeft, overschrijft de live rating deze prior.

Rationale: dit voorkomt systematische overschatting van promovendi in de eerste 8-10 speelrondes.

### 2. Competitie- en markt-specifieke EV thresholds
Bestanden:
- `football_agent/config/competitions.yml`
- `football_agent/models/value_engine.py`
- `football_agent/scripts/run_daily.py`

De ValueEngine accepteert nu:
- `custom_min_edge`
- `min_edge_by_market`

Hierdoor kan de engine lagere drempels hanteren in liquide markten zoals Premier League en Champions League, en hogere drempels in minder stabiele markten zoals Belgian Pro League en Conference League. Ook 1X2, Over/Under 2.5 en BTTS kunnen apart worden begrensd.

### 3. Game-State Normalized xG
Bestand:
- `football_agent/models/xg_model.py`

`TeamMatchPerformance` ondersteunt nu:
- `game_state_xg_for`
- `game_state_xg_against`
- `game_state_minutes`

Als deze data beschikbaar is, gebruikt het xG-model deze vóór raw xG. Daarmee weegt xG bij gelijke stand of binnen één doelpunt verschil zwaarder dan garbage-time xG bij ruime voorsprong of achterstand.

### 4. Data snapshot uitbreiding
Bestand:
- `football_agent/scripts/run_daily.py`

De run legt nu ook vast:
- promoted flags per team
- competitie-threshold
- markt-specifieke threshold-config

## Controle
Uitgevoerd:

```bash
python smoke_test.py
python -m unittest discover -s tests
python -m compileall football_agent -q
python -m football_agent.scripts.healthcheck
TELEGRAM_ENABLED=false python run_agent.py
python -m football_agent.scripts.run_backtest
python -m football_agent.scripts.run_weight_training
```

Resultaat:
- Smoke test OK
- 43 unit tests OK
- Compile check OK
- Healthcheck OK
- Daily run zonder API-keys crasht niet
- Backtest-script werkt
- Weight-training-script werkt

## Professioneel oordeel
V25.0.6 maakt de agent vooral robuuster voor de start van een nieuw seizoen. De engine is nu minder gevoelig voor promovendi-overschatting, gebruikt per competitie realistischere value-grenzen en kan xG schoner verwerken wanneer game-state splits beschikbaar zijn.
