# V25.1.2a — Odds Snapshot Idempotency Hotfix

## Build doel

V25.1.2a is een kleine hardening-release bovenop V25.1.2. De voorspellende logica, stakinglogica, pickselectie en modelversies blijven bewust ongewijzigd. Deze hotfix richt zich uitsluitend op database-hygiëne voor odds snapshots tijdens shadow testing en line-up monitor runs.

## Aanleiding

In V25.1.2 werd `snapshot_key` in `football_agent/database/repository.py` opgebouwd met de ruwe `snapshot.timestamp_utc`. Als een provider of scan dezelfde bookmaker/markt/selectie/odds meerdere keren met afwijkende seconden retourneert, kan de database dit als meerdere unieke snapshots zien.

Dat is onwenselijk tijdens de shadow-validatiefase, omdat het:

- `odds_snapshots` onnodig kan vullen;
- CLV- en odds-timeline analyse rommeliger maakt;
- herhaalde monitor-scans minder idempotent maakt;
- batch-upserts gevoeliger maakt voor dubbele conflict keys.

## Wijzigingen

### 1. Timestamp-normalisatie voor snapshot keys

Bestand:

- `football_agent/database/repository.py`

Toegevoegd:

- `normalize_odds_snapshot_timestamp_for_key(timestamp_utc)`
- `odds_snapshot_identity_key(fixture_id, snapshot)`

Gedrag:

- Provider timestamp blijft rauw bewaard in `snapshot_timestamp_utc`.
- Alleen de hash-input voor `snapshot_key` wordt genormaliseerd naar UTC-minuutniveau.
- Voorbeeld:
  - `2026-06-28T12:34:01Z`
  - `2026-06-28T12:34:59Z`
  - beide worden voor de key behandeld als `2026-06-28T12:34:00Z`.

### 2. Odds moves blijven uniek

De oddswaarde blijft onderdeel van de hash:

```text
fixture_id | bookmaker | market | selection | normalized_timestamp_minute | odds
```

Daardoor geldt:

- zelfde minuut + zelfde odds = zelfde snapshot key;
- zelfde minuut + gewijzigde odds = nieuwe snapshot key;
- volgende minuut + zelfde odds = nieuwe snapshot key.

### 3. Pre-upsert deduplicatie

`upsert_odds_snapshots(...)` bouwt nu eerst `rows_by_key` op voordat de Supabase upsert wordt uitgevoerd.

Effect:

- dubbele keys in dezelfde batch worden vooraf samengevoegd;
- Supabase krijgt geen payload met meerdere identieke `snapshot_key` records;
- het geretourneerde aantal is het aantal unieke rows dat daadwerkelijk naar upsert gaat.

## Bewust niet gewijzigd

Deze hotfix verandert niet:

- `MODEL_VERSION`;
- `CONFIG_VERSION`;
- pick identity;
- odds discovery;
- line-up monitor gedrag;
- Kelly staking;
- no-bet rules;
- Telegram/logica.

Reden: V25.1.2a is een database-idempotency hotfix, geen nieuw voorspellend model. Het modelversienummer gelijk houden voorkomt onnodige nieuwe pick identities voor dezelfde proposities tijdens shadow testing.

## Nieuwe testmodule

```text
tests/test_v25_1_2a_odds_snapshot_idempotency.py
```

Testdekking:

- UTC timestamp-normalisatie naar minuutniveau;
- timezone-normalisatie naar UTC;
- dezelfde minuut + dezelfde odds geeft dezelfde snapshot key;
- andere minuut of andere odds geeft een andere snapshot key;
- repository dedupliceert dezelfde-minute duplicate rows vóór upsert;
- echte odds moves binnen dezelfde minuut blijven aparte rows.

## Verwachte operationele impact

V25.1.2a maakt de Supabase odds snapshot laag schoner en veiliger voor de komende shadowfase. De agent blijft dezelfde picks maken als V25.1.2, maar schrijft odds snapshots idempotenter weg.
