# AUDIT V25.0.7 — Premium Telegram Operations Upgrade

## Doel

Deze versie maakt van de V25-engine niet alleen een model-engine, maar ook een premium Telegramgroep-operatie. De agent mag vaak draaien, maar moet weinig ruis veroorzaken. Het uitgangspunt blijft: veel scannen, alleen posten bij echte waarde of belangrijke statuswijzigingen.

## Geïmplementeerde upgrades

### 1. Loud vs silent Telegram policy

- Dagrapporten worden stil verstuurd met `disable_notification=True`.
- Heartbeats worden stil verstuurd.
- Ingetrokken picks worden stil verstuurd.
- Echte VALUE PICK-alerts worden luid verstuurd.

Dit zorgt ervoor dat leden leren: als de telefoon trilt, is er mogelijk actie nodig.

### 2. Notification State

Nieuw bestand:

`football_agent/storage/notification_state.py`

Functies:

- voorkomt dubbele VALUE PICK-alerts bij meerdere runs per dag;
- detecteert `WATCHLIST -> VALUE_PICK`;
- detecteert gewijzigde value-picks;
- detecteert ingetrokken picks;
- houdt heartbeat-sleutels bij zodat statusupdates niet blijven herhalen.

### 3. Event-driven line-up monitor

Nieuwe script:

`python -m football_agent.scripts.run_lineup_monitor`

Nieuwe workflow:

`.github/workflows/lineup-v25-monitor.yml`

De workflow draait elke 15 minuten tijdens het Europese voetbalvenster, maar analyseert alleen wedstrijden die in de T-65 tot T-45 minuten window vallen. Dit benadert een dynamische T-55 line-up check binnen GitHub Actions.

### 4. Heartbeat

Nieuw script:

`python -m football_agent.scripts.run_heartbeat`

Nieuwe workflow:

`.github/workflows/heartbeat-v25.yml`

Deze run stuurt een stille statusupdate wanneer er geen value picks zijn. Zo blijft de premiumgroep vertrouwen houden tijdens dagen zonder picks.

### 5. Live Sheet export

Nieuw bestand:

`football_agent/reports/live_sheet_export.py`

Output:

`output/live_picks_sheet.csv`

Optionele Telegram-link via GitHub variable:

`LIVE_SHEET_URL`

De agent pusht nog niet rechtstreeks naar Google Sheets, omdat dat extra service-account credentials vereist. De CSV is wel klaar voor transparante synchronisatie of read-only publicatie.

### 6. Premium Value Pick-alerts

Nieuwe Telegram-alert bevat:

- competitie en wedstrijd;
- markt en selectie;
- bookmaker en odds;
- minimum odds / fair odds;
- financiële EV en probability edge;
- stake in units;
- confidence, data quality en uncertainty;
- line-up status;
- modeluitleg via Gemini Explainer.

## Controle uitgevoerd

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

- Smoke test OK
- 48 unit tests OK
- Compile check OK
- Healthcheck OK
- Daily run crasht niet zonder API-keys
- Line-up monitor crasht niet zonder API-keys
- Heartbeat crasht niet zonder API-keys
- Backtest-script werkt
- Weight-training-script werkt

## Professioneel oordeel

V25.0.7 maakt de agent geschikter voor een betaalde Telegramgroep. De model-engine blijft streng, terwijl de communicatie nu premium aanvoelt: weinig ruis, duidelijke value-alerts, transparantie via live CSV en geruststellende stille statusupdates.

Belangrijke beperking: echte T-55 triggers zijn binnen GitHub Actions praktisch benaderd met een 15-minuten cron. Voor exacte event-driven scheduling zou later een always-on server of queue-worker nodig zijn.
