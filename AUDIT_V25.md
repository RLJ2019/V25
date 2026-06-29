# Audit V25 Multi-League Value Prediction Engine

Datum audit: 2026-06-19
Versie: V25.0.0-multi-league-value-engine

## 1. Doelcontrole

Doel van deze build: een nieuwe, modulaire multi-league value prediction engine bouwen op basis van de professionele ontwerpregel:

**Het model voorspelt. Gemini legt uit.**

De agent is niet gebouwd als gewone voorspeller die elke wedstrijd forceert, maar als scanner/filtermachine die alleen picks doorlaat bij voldoende odds, datakwaliteit, confidence en edge.

## 2. Scopecontrole

Opgenomen competities:

- Premier League
- Bundesliga
- Eredivisie
- Ligue 1
- Serie A
- La Liga
- Belgische Pro League
- Champions League
- Europa League
- Conference League

Nationale bekers zijn bewust niet opgenomen.

## 3. Modulecontrole

### Config

- `football_agent/config/competitions.yml` aanwezig.
- `football_agent/config/bookmaker_profiles.yml` aanwezig.
- `football_agent/config/model_settings.yml` aanwezig.
- `football_agent/config/loader.py` getest via healthcheck.

Controle: OK.

### Data modules

- `data/football_data.py`: client voor football-data.org.
- `data/api_football.py`: client voor API-Football fixtures, odds, injuries en lineups.
- `data/odds.py`: bookmaker-profielen, sharp/soft verrijking en odds-matrix.
- `data/fixtures.py`: multi-source fixture provider.
- `data/http.py`: retrybare HTTP-client.

Controle: OK. Live API-validatie vereist echte secrets.

### Market model

- `models/market_model.py` bevat raw implied probability, overround, no-vig probability, fair odds en Shin-achtige conservatieve correctie.
- Unit test controleert dat no-vig kansen optellen tot 1.0.
- Unit test controleert foutafhandeling bij ontbrekende 1X2 odds.

Controle: OK.

### Model modules

- `models/elo_model.py`: dynamische Elo-basis met updatefunctie.
- `models/xg_model.py`: xG-form estimate met fallback.
- `models/poisson_model.py`: scorematrix, 1X2, over/under en BTTS.
- `models/injury_model.py`: sleutelspeler-impact met niet-lineaire synergie en harde caps.
- `models/fatigue_model.py`: rustdagen, midweek, Europa en reisbelasting.
- `models/motivation_model.py`: meetbare motivatiefactoren.
- `models/referee_model.py`: beperkte chaosfactor.
- `models/calibration.py`: cluster-bucket structuur met minimum sample size.
- `models/ensemble.py`: combineert markt, model en feature-attributie.
- `models/value_engine.py`: berekent edge, fair odds en value-status.

Controle: OK.

### Decision modules

- `decision/no_bet_rules.py`: harde blokkades bij lage data/confidence/odds.
- `decision/pick_selector.py`: bepaalt VALUE_PICK, WATCHLIST of NO_BET.
- `decision/risk_filter.py`: extra veiligheidsfilter.

Controle: OK.

### Evaluation modules

- `evaluation/brier.py`
- `evaluation/log_loss.py`
- `evaluation/roi.py`
- `evaluation/closing_line_value.py`
- `evaluation/league_performance.py`
- `evaluation/calibration_buckets.py`

Controle: OK.

### Reports

- `reports/telegram.py`: bouwt Telegrambericht.
- `reports/gemini_explainer.py`: Gemini mag alleen harde model-output uitleggen.
- `reports/daily_summary.py`
- `reports/weekly_evaluation.py`

Controle: OK.

### Storage

- `storage/prediction_log.py`: CSV-log van picks.
- `storage/odds_snapshots.py`: CSV-log van odds met timestamp/bookmaker/profile.
- `storage/model_versions.py`: modelversie.

Controle: OK.

### Scripts

- `run_agent.py`: startpunt.
- `football_agent/scripts/run_daily.py`: dagelijkse run.
- `football_agent/scripts/healthcheck.py`: configuratiecheck.
- `football_agent/scripts/run_backtest.py`: backtest-ingang voorbereid.

Controle: OK.

## 4. Testresultaten

Uitgevoerd:

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
Ran 10 tests in 0.003s
OK
```

Compilecheck: OK.

Healthcheck: OK.

Dagelijkse run zonder API-keys: OK, agent crasht niet en geeft correct 0 wedstrijden / geen picks.

## 5. Professionele risicocontrole

### Goed geborgd

- Geen value pick zonder odds.
- Geen value pick bij lage datakwaliteit.
- Geen value pick bij lage confidence.
- Odds worden no-vig gecorrigeerd.
- Sharp/soft bookmakerprofielen zijn voorbereid.
- Feature-attributie is aanwezig.
- Gemini krijgt geen beslissingsmacht.
- CSV logging is aanwezig.
- Evaluatiemodules zijn aanwezig.
- GitHub Actions workflow is aanwezig.

### Belangrijke beperking

De agent is technisch werkend, maar de echte voorspellende kwaliteit kan pas worden vastgesteld met:

1. Verse oddsdata.
2. Closing odds.
3. Historische odds/backtestdata.
4. Betrouwbare injuries/lineups/teamstats.
5. Minimaal enkele honderden geëvalueerde picks per cluster.

Zonder betaalde/API-toegang zal V25 streng filteren en vooral NO_BET geven. Dat is correct gedrag.

## 6. Backtesting-status

Backtest-entrypoint is aanwezig, maar echte backtesting vereist historische datasets:

- `historical_fixtures.csv`
- `historical_odds.csv`
- `historical_results.csv`
- optioneel: `historical_closing_odds.csv`

Backtestlogica moet worden uitgebreid zodra de datasets beschikbaar zijn.

## 7. Security-check

- Geen secrets hardcoded.
- API-keys uitsluitend via environment variables / GitHub Secrets.
- Telegram-token niet opgeslagen in code.
- Output wordt via `output/` gelogd.

Controle: OK.

## 8. Eindbeoordeling

De V25-agent is gebouwd als een professionele basisversie van de multi-league value engine. De architectuur volgt het plan: markt eerst, model erbovenop, strenge pickselectie, feature-attributie, logging, evaluatie en Telegramrapportage.

Status: **technisch gereed als V25.0.0 basisbuild**.

Niet claimen: dat het model de markt al verslaat. Dat moet via backtesting en live-evaluatie worden bewezen.

Professionele conclusie:

**Deze build is geschikt als fundament. De volgende kwaliteitsstap is niet meer modules toevoegen, maar echte data aansluiten en backtesten.**
