# ChatGPT Validation — V25.1.2a Odds Snapshot Idempotency

## Bron

Gebaseerd op de eerder gevalideerde build:

```text
v25_multi_league_value_engine_v25_1_2_validated_chatgpt.zip
```

## Doel van V25.1.2a

Kleine hotfix vóór shadow testing. De build normaliseert odds snapshot timestamps naar UTC-minuutniveau voor `snapshot_key`, dedupliceert dubbele snapshot keys vóór Supabase upsert en behoudt echte odds moves als aparte snapshots.

## Gewijzigde bestanden

```text
football_agent/database/repository.py
tests/test_v25_1_2a_odds_snapshot_idempotency.py
AUDIT_V25_1_2A_ODDS_SNAPSHOT_IDEMPOTENCY.md
SETUP_V25_1_2A_ODDS_SNAPSHOT_IDEMPOTENCY.md
README.md
BUILD_MANIFEST_V25_1_2A.json
```

## Belangrijk ontwerpbesluit

`MODEL_VERSION`, `CONFIG_VERSION`, `FEATURE_SET_VERSION` en `CALIBRATION_VERSION` zijn bewust niet gewijzigd. V25.1.2a verandert geen voorspellend model, pick identity, staking of line-up monitor logica. Dit voorkomt onnodige nieuwe pick identities tijdens de shadowfase.

## Uitgevoerde checks

```text
python -m compileall football_agent -q
python smoke_test.py
python -m unittest discover -s tests
python -m football_agent.scripts.healthcheck
TELEGRAM_ENABLED=false python run_agent.py
TELEGRAM_ENABLED=false python -m football_agent.scripts.run_lineup_monitor
DATABASE_ENABLED=true DATABASE_SHADOW_MODE=true SHADOW_COMPARE_FAIL_CLOSED=true python -m football_agent.scripts.compare_shadow_state
```

## Resultaat

```text
Compile check: OK
Smoke test: OK
Unit tests: OK — 82 tests passed
Healthcheck: OK
Daily run zonder API-keys: OK
Line-up monitor zonder API-keys: OK
Shadow compare zonder Supabase secrets: SKIPPED met critical_errors=0
```

## Conclusie

V25.1.2a is geschikt om naar GitHub te uploaden als laatste hotfix vóór de 5-speeldagen shadow-validatie.
