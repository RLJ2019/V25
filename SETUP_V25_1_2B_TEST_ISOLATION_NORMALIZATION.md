# SETUP V25.1.2b — Test Isolation & No-Bet Normalization

## Aanbevolen procedure

1. Push deze V25.1.2b build naar GitHub.
2. Maak Supabase shadow-data schoon met `SUPABASE_CLEAN_SHADOW_TABLES_V25_1_2B.sql`.
3. Draai in GitHub Actions:
   - `Daily V25 Multi-League Agent` met `mode=healthcheck`
   - `Daily V25 Multi-League Agent` met `mode=database_healthcheck`
   - `Daily V25 Multi-League Agent` met `mode=daily`
   - `Daily V25 Multi-League Agent` met `mode=compare_shadow`
4. Verwacht bij de eerste schone validatie:
   - `critical_errors = 0`
   - `status = PASS`
   - `shadow_parity_percent = 100.0`

## Belangrijk

Laat `TELEGRAM_ENABLED=false` tijdens deze validatie. Verhoog `MAX_MATCHES` pas nadat daily + compare_shadow groen zijn.
