# Installatiechecklist V25.1.0 Shadow Database

## 1. Eerst veilig uploaden

Upload de volledige build naar GitHub. Laat voorlopig staan:

```text
DATABASE_ENABLED=false
DATABASE_SHADOW_MODE=true
DATABASE_FAIL_OPEN=true
```

Run daarna de daily workflow. De bestaande agent moet exact blijven werken en in de artifacts hoort `shadow_database_report.json` te staan met `active: false`.

## 2. Database aanmaken

Open Supabase → SQL Editor en voer uit:

```text
football_agent/database/migrations/001_initial_schema.sql
```

Controleer dat deze tabellen bestaan:

```text
fixtures
picks
pick_events
notification_state_shadow
odds_snapshots
settlements
workflow_runs
sync_jobs
```

## 3. GitHub Secrets

```text
SUPABASE_URL
SUPABASE_SECRET_KEY
```

Gebruik geen gewone repository variable voor de secret key.

## 4. GitHub Variables

```text
DATABASE_ENABLED=true
DATABASE_SHADOW_MODE=true
DATABASE_FAIL_OPEN=true
DATABASE_TIMEOUT_SECONDS=20
DATABASE_MAX_RETRIES=2
DATABASE_BATCH_SIZE=250
SHADOW_COMPARE_SINCE_UTC=
```

## 5. Healthcheck

Actions → Daily V25 Multi-League Agent → Run workflow → mode:

```text
database_healthcheck
```

De run moet groen worden. Download het artifact en open `database_healthcheck.json`.

## 6. Eerste shadow run

Run mode:

```text
daily
```

Controleer:

```text
Shadow database: enabled=True configured=True active=True mode=shadow fail_open=True
```

In het artifact:

```text
shadow_database_report.json
```

`failures` moet leeg zijn.

## 7. Vergelijking

Na meerdere runs kies je mode:

```text
compare_shadow
```

Controleer `shadow_parity_report.json`. Een `REVIEW` in de eerste dagen is mogelijk wanneer de database later is aangezet dan de bestaande CSV-historie. Vanaf het activatiemoment moet nieuwe data wel gelijklopen.

## 8. Niet doen in Phase 1

- GitHub-cache verwijderen.
- Telegramstate uit de database lezen.
- Lokale CSV/JSON uitschakelen.
- Settlement live activeren.
- De Supabase secret key delen of publiceren.
