# AUDIT V25.1.2b — Test Isolation & No-Bet Normalization

## Doel

Deze hotfix voorkomt CI-pijplijnvervuiling van Supabase en verwijdert een fantoommismatch in de shadow compare voor NO_BET-rijen.

## Wijzigingen

### 1. GitHub Actions test-isolatie

De teststappen in de workflows die unit tests uitvoeren schakelen database-toegang expliciet uit:

- `.github/workflows/daily-v25-agent-fixed.yml`
- `.github/workflows/weekly-v25-recalibration.yml`

Lokale test-env per teststap:

```yaml
DATABASE_ENABLED: "false"
SUPABASE_URL: ""
SUPABASE_SECRET_KEY: ""
```

Hierdoor kunnen unit tests nooit meer naar de live Supabase-cloud schrijven, ook niet wanneer job-level database secrets aanwezig zijn.

`heartbeat-v25.yml` en `lineup-v25-monitor.yml` bevatten geen unit-teststap in deze codebase en zijn daarom niet aangepast met een test-env block.

### 2. NO_BET probability-normalisatie

`football_agent/scripts/compare_shadow_state.py` behandelt een lokale lege kanswaarde en databasewaarde `0.0` als equivalent wanneer er geen actieve selectie of markt is:

- `selection` leeg of `NONE`, of
- `market` leeg of `NONE`, en
- veld is `model_probability` of `market_probability`.

Echte mismatches voor actieve markten blijven strict fail-closed.

### 3. Metadata

`football_agent/storage/model_versions.py` is bijgewerkt naar:

- `MODEL_VERSION = "V25.1.2b-test-isolation-normalization"`
- `CONFIG_VERSION = "2026-06-28-v25.1.2b-hardening"`
- `FEATURE_SET_VERSION = "v25.1.2b-test-isolation"`
- `CALIBRATION_VERSION = "v25.0.9-candidate-weights"`

## Validatie

Toegevoegd:

- `tests/test_v25_1_2b_test_isolation_normalization.py`

Dekking:

- NO_BET null-vs-zero probability equivalentie.
- Actieve marktprobability mismatch blijft zichtbaar.
- Daily workflow teststap wist Supabase env.
- Weekly workflow teststap wist Supabase env.
- V25.1.2b metadata klopt.
