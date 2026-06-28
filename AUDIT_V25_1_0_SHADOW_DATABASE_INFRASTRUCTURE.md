# Audit V25.1.0 Phase 1 — Shadow Database Infrastructure

## Doel

Een centrale, auditeerbare database toevoegen zonder het bewezen V25.0.9-gedrag te vervangen.

## Implementatie

### Database package

```text
football_agent/database/
├── __init__.py
├── connection.py
├── models.py
├── repository.py
├── shadow_writer.py
└── migrations/001_initial_schema.sql
```

### Nieuwe scripts

```text
python -m football_agent.scripts.run_database_healthcheck
python -m football_agent.scripts.compare_shadow_state
```

### Dual write

`run_daily.py` blijft lokaal schrijven en spiegelt daarnaast:

- fixtures;
- odds snapshots;
- picks;
- observation events;
- notification-state en alert-events;
- workflow-run metadata.

### Fail-open

Bij `DATABASE_FAIL_OPEN=true`:

- databasefouten worden gelogd;
- `shadow_database_failures.jsonl` wordt aangemaakt;
- de modelrun gaat door;
- Telegram wordt niet geblokkeerd;
- CSV/JSON blijven normaal functioneren.

### Idempotency

- `pick_id`: deterministische UUIDv5.
- `identity_key`: fixture + market + selection + model version.
- `event_key`: SHA-256 op identity + event + signature.
- `snapshot_key`: SHA-256 op fixture + bookmaker + market + selection + timestamp + odds.

## Tests

Toegevoegd: `tests/test_v25_1_0_shadow_database.py`.

Gecontroleerd:

- stabiele pick-identiteit bij odds/bookmakerwijziging;
- dual-write calls;
- fail-open gedrag;
- secrets verschijnen niet in veilige configuratielogs;
- volledige bestaande regressiesuite;
- historische fixturemodus voor 2024 en aliases `football-data` / `api-football`;
- herhaling van een niet-verzonden Value Pick zodra Telegram later wordt aangezet.

## Resultaat

```text
V25 smoke test OK
Ran 72 tests
OK
Compile check OK
Daily run met DATABASE_ENABLED=false OK
Database healthcheck disabled path OK
Shadow parity disabled path OK
Alle workflow-YAML-bestanden parseren geldig
```

## Bewuste beperkingen

- Supabase/PostgreSQL is nog niet de source of truth.
- Settlement is nog niet live.
- `settlements` is alleen voorbereid in het schema.
- Exact T-2 closing-line capture is niet toegevoegd.
- Google Sheet is nog niet database-gedreven.
- Telegram gebruikt nog de lokale NotificationState.

## Go/no-go voor Phase 2

No-go totdat minimaal vijf speeldagen een parity van 100% tonen zonder database-duplicaten of state-mismatches.
