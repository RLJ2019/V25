# AUDIT V25.0.9 — Premium Reliability & Sharp Market Upgrade

## Doel
Deze versie verwerkt de premium-community en pro-bettor auditpunten uit V25.0.8. De nadruk ligt op betrouwbaarheid voor een betaalde Telegramgroep: urgente alerts, minder technisch jargon, betere state-bescherming, scherper markttransparantie en robuustere webhook-sync.

## Implementaties

### 1. Withdrawal alerts zijn nu luid
- `NotificationState.classify_pick()` markeert `value_pick_withdrawn` nu met `disable_notification=False`.
- `run_daily.py` verstuurt withdrawals expliciet luid.
- `TelegramReporter.build_withdrawal_alert()` gebruikt urgentere tekst.

Reden: een intrekking is net zo belangrijk als de oorspronkelijke Value Pick, omdat leden al kunnen hebben ingezet.

### 2. Gemini-uitleg zonder technisch jargon
- `gemini_explainer.py` verbiedt expliciet termen zoals logit, Poisson, Dixon-Coles, overround, Shin, isotonic regression, decay, bootstrap, Monte Carlo, Brier en CLV.
- Fallback-uitleg vertaalt modeldata naar normale sporttaal.

Reden: premiumleden willen begrijpelijke besluitvorming, geen wiskundige ruis.

### 3. Gedeelde workflow-concurrency
- Alle state-schrijvende GitHub Actions gebruiken nu dezelfde concurrency group: `v25-football-agent-state`.
- Dit verkleint race conditions tussen daily run, line-up monitor, heartbeat en recalibration.

Let op: voor echte commerciële productie blijft een centrale database of object-store met locking aanbevolen.

### 4. Atomic notification state save
- `notification_state.py` schrijft nu eerst naar `.tmp` en vervangt daarna atomisch via `os.replace`.
- Corruptie door gedeeltelijke writes wordt daarmee beperkt.

### 5. Live Sheet webhook met retry en idempotency
- `LiveSheetExporter.push_webhook()` stuurt nu een `idempotency_key` mee.
- Webhook krijgt retry-logica.
- Definitieve failures worden gelogd in `output/live_sheet_webhook_failures.jsonl`.
- De CSV/prediction log blijft de bron van waarheid; Google Sheet is alleen een spiegel.

### 6. Staking opgeschoond
- Triple-discounting is vervangen door één blended risk multiplier.
- NoBetRules filtert eerst zwakke picks; daarna blijft de stake defensief, maar niet onnodig kapotgedrukt.
- Fractional Kelly blijft standaard 0.15 met dynamische caps.

### 7. Sharp/no-vig market transparency
- `ValueDecision` bevat nu:
  - `baseline_source`
  - `sharp_market_probability`
  - `sharp_fair_odds`
  - `selected_odds_profile`
- Telegram toont nu `Sharp/no-vig fair odds` naast bookmaker odds en minimum odds.

### 8. Markt-attributie voorbereid per markt
- Nieuwe module: `models/market_attributors.py`.
- Attributie is opgesplitst in:
  - `OneXTwoAttributor`
  - `OverUnderAttributor`
  - `BTTSAttributor`
- Gemini krijgt nu marktspecifieke uitleg bij 1X2, Over/Under en BTTS.

### 9. Order-invariant logit-attributie
- `EnsembleModel._apply_logit_attribution()` is herbouwd.
- Alle features worden vanaf dezelfde baseline naar logit-delta’s geconverteerd en daarna bij elkaar opgeteld.
- De uitkomst is daardoor niet langer afhankelijk van de volgorde waarin features staan.

### 10. Smooth calibration tails
- `CalibrationModel.calibrate_probability()` gebruikt nu logit-extrapolatie buiten de PAV-segmenten.
- Dit voorkomt abrupte EV-sprongen aan de uiterste staarten.

## Uitgevoerde checks

```bash
python -m compileall football_agent -q
python smoke_test.py
python -m unittest discover -s tests
python -m football_agent.scripts.healthcheck
TELEGRAM_ENABLED=false python run_agent.py
TELEGRAM_ENABLED=false python -m football_agent.scripts.run_lineup_monitor
TELEGRAM_ENABLED=false python -m football_agent.scripts.run_heartbeat
python -m football_agent.scripts.run_backtest
python -m football_agent.scripts.run_weight_training
```

Resultaat:

- Compile check: OK
- Smoke test: OK
- Unit tests: 61 tests OK
- Healthcheck: OK
- Daily run zonder API-keys: crasht niet
- Line-up monitor zonder API-keys: crasht niet
- Heartbeat zonder API-keys: crasht niet
- Backtest-script: werkt met correcte instructie-output zonder inputdata
- Weight-training-script: werkt met veilige candidate-output zonder promotie bij te weinig data

## Professioneel oordeel
V25.0.9 is vooral een premium reliability upgrade. De agent is nu beter geschikt voor een betaalde Telegramgroep omdat kritieke statuswijzigingen luid worden verstuurd, de uitleg begrijpelijker is, staking minder dubbel wordt gestraft en de markttransparantie richting leden hoger is.

## Resterende aandachtspunten voor productie

1. GitHub Actions + cache blijft prima voor test/early production, maar een betaalde groep vraagt uiteindelijk om Supabase/PostgreSQL of object storage met locking.
2. De Google Sheet moet een spiegel blijven, niet de bron van waarheid.
3. Test met echte oddsdata moet aantonen of de nieuwe stakingverdeling retentie en ROI verbetert.
4. Voor volledig event-driven line-up checks blijft een always-on worker beter dan GitHub cron.
