# AUDIT V25.0.5 — Risk, xG90 & Recalibration Upgrade

## Doel
Deze versie verwerkt de professionele aanbevelingen voor betrouwbaarheid, risicobeheersing en datavalidatie:

1. xG normaliseren naar xG per 90 minuten.
2. International-break onzekerheidsfilter toevoegen.
3. Fractional Kelly gebruiken als conservatieve stake-indicatie.
4. Gewichten-training ombouwen naar candidate recalibration in plaats van blind auto-pushen.
5. Backtest-integriteit versterken tegen lookahead bias.
6. Markt-specifieke backtest/evaluatie voor 1X2, Over/Under en BTTS ondersteunen.

## Belangrijkste wijzigingen

### 1. xG90-normalisatie
Bestand: `football_agent/models/xg_model.py`

- `TeamMatchPerformance` heeft nu `minutes_played`.
- Match-level xG en goals worden naar per-90 omgerekend voordat time-decay wordt toegepast.
- Dit vermindert data drift door langere blessuretijd en maakt oudere xG-data beter vergelijkbaar met moderne wedstrijden.

### 2. International Break Filter
Bestanden:

- `football_agent/models/calendar_context.py`
- `football_agent/models/uncertainty_model.py`
- `football_agent/models/ensemble.py`
- `football_agent/decision/no_bet_rules.py`

Wijzigingen:

- Nieuwe `InternationalBreakFilter` met configureerbare windows via `INTERNATIONAL_BREAK_WINDOWS`.
- Eerste clubronde na interlandbreak krijgt een hogere onzekerheidsmarge.
- Confidence wordt gecapt op maximaal 7/10.
- Value Picks zonder bevestigde line-up worden geblokkeerd na een interlandbreak.

### 3. Fractional Kelly Stake Indicatie
Bestanden:

- `football_agent/decision/staking.py`
- `football_agent/decision/pick_selector.py`
- `football_agent/decision/exposure_manager.py`
- `football_agent/storage/prediction_log.py`
- `football_agent/reports/telegram.py`

Wijzigingen:

- Nieuwe conservatieve Fractional Kelly-module.
- Kelly wordt gediscount door uncertainty, datakwaliteit en confidence.
- Staking is een risicostake-indicatie, geen harde instructie.
- ExposureManager bevat nu een daglimiet op totale units.
- Bij downgrade naar Watchlist wordt stake automatisch op 0 gezet.

### 4. Candidate Recalibration
Bestand: `football_agent/scripts/run_weight_training.py`

Wijzigingen:

- Training schrijft standaard `output/candidate_learned_model_weights.json`.
- Er wordt een `output/weight_training_report.json` gemaakt.
- Candidate weights worden gevalideerd tegen productie via log-loss.
- Productiegewichten worden niet automatisch overschreven.
- Promotie kan alleen handmatig of met `PROMOTE_WEIGHTS=true` en voldoende verbetering.

### 5. Weekly Candidate Recalibration Workflow
Bestand: `.github/workflows/weekly-v25-recalibration.yml`

- Draait wekelijks op maandag.
- Genereert candidate weights en rapport.
- Uploadt artifact.
- Pusht niet automatisch naar main.

### 6. Backtest Integriteit
Bestand: `football_agent/scripts/run_backtest.py`

Wijzigingen:

- Checkt lookahead bias via `prediction_time_utc`, `kickoff_utc` en `odds_timestamp_utc` als aanwezig.
- Rijen met data na aftrap worden uitgesloten.
- Rapport toont integrity warnings.
- Rapport splitst prestaties per markt.
- Stakes uit `stake_units` worden meegenomen in ROI wanneer aanwezig.

## Extra correctie
In `ensemble.py` is ook de dubbele AWAY-Elo-inversie verwijderd. Dit was een verborgen nauwkeurigheidsrisico: de away-selectie kreeg anders per ongeluk geen tegengestelde Elo-correctie.

## Testresultaten
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

- Smoke test: OK
- Unit tests: 39 tests OK
- Compile check: OK
- Healthcheck: OK
- Daily run zonder API-keys: crasht niet
- Backtest zonder inputdata: geeft correcte instructie-output
- Weight training zonder historische data: maakt candidate/report en weigert veilige promotie

## Professionele beoordeling
V25.0.5 maakt de agent niet alleen slimmer, maar vooral defensiever en beter auditable. De belangrijkste verbetering is dat de agent nu sterker onderscheid maakt tussen model-edge en uitvoerbaar risico.

Deze versie is bewust strenger:

- Meer Watchlist/No Bet na interlandbreaks.
- Geen officiële Value Pick zonder voldoende line-up en datakwaliteit.
- Kelly-stake wordt verlaagd bij hoge onzekerheid.
- Gewichten worden niet blind automatisch gepromoveerd.
- Backtests worden beschermd tegen lookahead bias.

## Resterende afhankelijkheden
Voor echte voorspellende kracht blijven nodig:

- Betrouwbare historische odds inclusief timestamp en closing odds.
- Echte xG/teamstats met minuteninformatie.
- Line-ups en blessuredata met bronzekerheid.
- Voldoende live picks voor candidate recalibration.

## Eindoordeel
V25.0.5 is de sterkste en meest risicobewuste build tot nu toe. De agent is klaar om als live value-scanner getest te worden, maar moet eerst voldoende historische/live data verzamelen voordat candidate weights veilig naar productie mogen.
