# ChatGPT Validation — V25.1.2b Test Isolation & No-Bet Normalization

## Build

Version: `V25.1.2b-test-isolation-normalization`

## Implemented changes

1. GitHub Actions unit-test isolation:
   - `.github/workflows/daily-v25-agent-fixed.yml`
   - `.github/workflows/weekly-v25-recalibration.yml`

   The test steps now override database env vars locally:

   ```yaml
   DATABASE_ENABLED: "false"
   SUPABASE_URL: ""
   SUPABASE_SECRET_KEY: ""
   ```

   This prevents CI tests from writing to Supabase even when job-level secrets are configured.

2. Shadow compare NO_BET normalization:
   - `football_agent/scripts/compare_shadow_state.py`

   Empty local probabilities and database `0.0` probabilities are treated as equivalent for no-active-market/no-active-selection rows only. Active market mismatches remain strict.

3. Version metadata updated:
   - `football_agent/storage/model_versions.py`

4. Added cleanup SQL:
   - `SUPABASE_CLEAN_SHADOW_TABLES_V25_1_2B.sql`

## Validation performed

```text
python -m compileall football_agent -q
python smoke_test.py
python -m unittest discover -s tests
TELEGRAM_ENABLED=false DATABASE_ENABLED=false python -m football_agent.scripts.healthcheck
TELEGRAM_ENABLED=false DATABASE_ENABLED=false python run_agent.py
TELEGRAM_ENABLED=false DATABASE_ENABLED=false python -m football_agent.scripts.run_lineup_monitor
DATABASE_ENABLED=false SHADOW_COMPARE_FAIL_CLOSED=true python -m football_agent.scripts.compare_shadow_state
```

## Results

```text
Compile check: OK
Smoke test: OK
Unit tests: OK — 87 tests passed
Healthcheck without secrets: OK
Daily run without API keys: OK
Line-up monitor without API keys: OK
Shadow compare with database disabled: SKIPPED, critical_errors=0
```

## Required manual step before first V25.1.2b GitHub daily run

Run `SUPABASE_CLEAN_SHADOW_TABLES_V25_1_2B.sql` in Supabase SQL Editor to remove polluted shadow-test rows from the previous run.
