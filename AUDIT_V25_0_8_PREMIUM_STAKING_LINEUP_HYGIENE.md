# Audit V25.0.8 — Premium Staking, Line-up Hygiene & Member Trust

## Build
`V25.0.8-premium-staking-lineup-hygiene`

## Doel
Deze release hardent de premium Telegram-community laag van de V25 engine. De nadruk ligt op bankrollbescherming, duidelijke unitcommunicatie, minder notificatieruis, watchlist-gerichte line-up checks en transparantie via live sheet export.

## Geïmplementeerde wijzigingen

### 1. Defensieve unit-staking
- `decision/staking.py` gebruikt nu een defensievere fractional Kelly standaard (`0.15`).
- Max units per pick is standaard 2.0, maar dynamisch lager bij hogere onzekerheid of lagere data/confidence.
- Unitadvies wordt afgerond naar conservatieve 0.25-unit stappen.
- Bij te hoge onzekerheid, te lage data of te lage confidence wordt stake automatisch 0.0.
- `NoBetRules` blokkeert officiële Value Picks wanneer de stake-indicatie onder de minimumgrens valt.

### 2. Min. odds voor value
- `ValueEngine` berekent nu `min_acceptable_odds`.
- Dit is niet alleen fair odds, maar odds inclusief de vereiste financiële EV-threshold.
- Telegram toont voortaan `Min. odds voor value`, zodat leden niet achter slechte odds aanlopen.

### 3. Watchlist-gerichte line-up monitor
- De line-up monitor scant nog steeds rond T-65 tot T-45 minuten, maar kan nu beperkt worden tot eerdere `WATCHLIST` en `VALUE_PICK` fixtures.
- Dit verlaagt API-verbruik en Telegramruis.
- Exacte seconde-precisie blijft niet haalbaar met GitHub Actions; de 15-minuten monitor is de praktische benadering.

### 4. Telegram discipline
- Value Pick alerts blijven luide meldingen.
- Daily reports, heartbeats en withdrawals blijven stil.
- Pick alerts vermelden nu dat units bankroll-eenheden zijn, geen euroadvies.
- Pick alerts bevatten discipline-waarschuwing: geen chasing wanneer minimum odds gemist zijn.

### 5. Live Sheet webhook bridge
- `LiveSheetExporter` schrijft nog steeds `output/live_picks_sheet.csv`.
- Optioneel kan `GOOGLE_SHEET_WEBHOOK_URL` worden ingesteld om rows naar een Google Apps Script webhook te pushen.
- Hierdoor kan een read-only Google Sheet als publieke transparantielaag gebruikt worden zonder extra Python dependencies.

## Tests uitgevoerd

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

## Resultaat
- Smoke test OK
- Unit tests: 53 tests OK
- Compile check OK
- Healthcheck OK
- Daily run zonder API-keys crasht niet
- Line-up monitor crasht niet
- Heartbeat crasht niet
- Backtest-script werkt
- Weight-training-script werkt

## Professioneel oordeel
V25.0.8 verhoogt niet zozeer de ruwe modelkracht, maar wel de commerciële betrouwbaarheid van de premium Telegramgroep. De agent is nu duidelijker, minder spamgevoelig en defensiever in staking. Dat is belangrijk voor ledenretentie en bankrollbescherming.

## Open aandachtspunten
- Voor echte T-55 precisie is later een always-on worker of queue-scheduler nodig.
- Voor live Google Sheet sync moet een Google Apps Script webhook of vergelijkbare bridge worden ingericht.
- Unitadvies blijft een risico-indicatie; communicatie naar leden moet altijd benadrukken dat 1 unit persoonlijk bepaald wordt.
