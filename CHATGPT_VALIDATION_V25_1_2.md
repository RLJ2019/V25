# ChatGPT Validation — V25.1.2

Datum: 2026-06-28

## Scope

Deze controle is uitgevoerd op de aangeleverde ZIP `v25_multi_league_value_engine_v25_1_2_shadow_hardening_operational_efficiency(2).zip`.

## Gecontroleerde V25.1.2-punten

- Bulk odds discovery groepeert per league/season in plaats van per league/date.
- Line-up monitor schakelt bulk odds discovery uit en valt terug op real-time fixture odds.
- Fractional Kelly bevat een longshot-deflator bij decimal odds boven 4.00.
- Shadow compare bevat fail-closed gedrag via `SHADOW_COMPARE_FAIL_CLOSED=true`.
- GitHub workflows bevatten `SHADOW_COMPARE_FAIL_CLOSED`.

## Uitgevoerde checks

```bash
python -m compileall football_agent -q
python smoke_test.py
python -m unittest discover -s tests
python -m football_agent.scripts.healthcheck
TELEGRAM_ENABLED=false LOCAL_OUTPUT_DIR=/mnt/data/v25_work/run_output python run_agent.py
TELEGRAM_ENABLED=false LOCAL_OUTPUT_DIR=/mnt/data/v25_work/lineup_output python -m football_agent.scripts.run_lineup_monitor
TELEGRAM_ENABLED=false LOCAL_OUTPUT_DIR=/mnt/data/v25_work/heartbeat_output python -m football_agent.scripts.run_heartbeat
LOCAL_OUTPUT_DIR=/mnt/data/v25_work/compare_output python -m football_agent.scripts.compare_shadow_state
```

## Resultaat

- Compile check: OK
- Smoke test: OK
- Unit tests: OK — 77 tests passed
- Healthcheck: OK
- Daily run zonder API-keys: OK, geen crash
- Line-up monitor zonder API-keys: OK, odds discovery correct uitgeschakeld
- Heartbeat zonder API-keys: OK, geen crash
- Shadow compare zonder databaseconfiguratie: OK, status `SKIPPED` met `critical_errors=0`

## Conclusie

De aangeleverde ZIP is technisch consistent als V25.1.2-build. Er hoefden geen extra core-codewijzigingen bovenop deze V25.1.2-ZIP te worden toegepast.
