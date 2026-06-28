# Audit V25.0.1 — Gemini audit fixes

## Doel
Deze patch verwerkt de kritieke punten uit de Gemini-audit op V25.0.0.

## Verwerkte fixes

### 1. Ensemble-attributie gecontroleerd en versterkt
- De door Gemini genoemde argument-mismatch is gecontroleerd.
- In de actuele code was de call-signature reeds consistent, maar de module is alsnog strakker gemaakt door expliciete named arguments te gebruiken.
- `_build_attribution(...)` accepteert nu expliciet:
  - `xg_delta`
  - `injury_delta`
  - `fatigue_delta`
- Dit vermindert de kans op positional-argument fouten.

### 2. xG-attributie niet langer hardcoded nul
- De oude `xg_adj = 0.0` is verwijderd.
- Het model berekent nu een echte xG-bijdrage via `XGModel.adjustment_pp(adj_home_xg, adj_away_xg)`.
- HOME, AWAY en DRAW krijgen elk een expliciete xG-bijdrage in de Feature Attribution Matrix.

### 3. Log-loss gecontroleerd
- `evaluation/log_loss.py` retourneert correct `-math.log(p)`.
- Extra unit test toegevoegd op positieve log-loss en bekende waarde `-ln(0.5)`.

### 4. Value Engine omgebouwd naar financiële Expected Value
- De primaire `edge` is nu de echte financiële EV:
  - `expected_value = (model_probability * decimal_odds) - 1`
- De oude kansdelta blijft beschikbaar als `probability_edge`.
- `best_value(...)` sorteert nu op `expected_value` in plaats van op ruwe probability edge.
- Telegram en prediction log tonen nu EV én probability edge.

### 5. Market-cleansing guardrail toegevoegd
- `MatchAnalysis` heeft nu:
  - `market_cleansing_failed`
  - `market_probabilities_are_fallback`
- `run_daily.py` geeft deze vlag door aan het ensemble.
- `NoBetRules` blokkeert automatisch Value Picks bij:
  - market cleansing failure
  - fallback market baseline
- `PickSelector` laat bij kritieke market-violations geen Watchlist/Value Pick meer door als de marktbaseline onbetrouwbaar is.

## Nieuwe tests
Toegevoegd:
- `tests/test_ensemble_guardrails.py`

Uitgebreide testdekking toegevoegd voor:
- xG-attribution niet nul bij xG-verschil
- fallback-markt blokkeert Value Pick zelfs als odds aanwezig zijn
- Value Engine sorteert op financiële EV, niet op ruwe kansedge
- log-loss positieve output

## Uitgevoerde checks

```bash
python smoke_test.py
python -m unittest discover -s tests
python -m compileall football_agent -q
python -m football_agent.scripts.healthcheck
TELEGRAM_ENABLED=false python run_agent.py
```

Resultaat:

```text
V25 smoke test OK
Ran 13 tests
OK
Compile check OK
Healthcheck OK
Daily run zonder API-keys crasht niet
```

## Eindoordeel
V25.0.1 is technisch sterker dan V25.0.0. De kritieke runtime-/logicapunten uit de Gemini-audit zijn verwerkt. De agent is nu strenger op marktdata, rekent value financieel correcter uit en geeft geen pick meer op basis van fallback-market fantoomedges.

## Belangrijke beperking
Deze versie blijft een technisch fundament. Voor echte voorspelkracht zijn live en historische data nodig:
- betrouwbare odds inclusief timestamps
- opening/current/closing odds
- xG/teamstats
- blessures/line-ups
- backtesting over meerdere seizoenen
