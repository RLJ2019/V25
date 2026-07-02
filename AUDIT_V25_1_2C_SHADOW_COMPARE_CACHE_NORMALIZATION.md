# V25.1.2c — Shadow Compare Cache Normalization

## Scope

V25.1.2c is a narrow hotfix for multi-run shadow validation. It does not change prediction logic, staking logic, odds discovery, model weights, or database schema.

## Problems fixed

1. `prediction_log.csv` is append-only and restored from GitHub Actions cache. The same future proposition can appear more than once across daily runs. Compare now deduplicates local rows by `identity_key` and keeps the newest/most complete row.
2. Local notification state can contain orphan/stale items from cached runs. Compare now filters notification-state parity to the current pick identity set.
3. Non-1X2 value picks such as `OVER_UNDER_2_5|OVER_2_5` could not derive selected probability from `model_home/draw/away`. The prediction log now stores `selected_model_probability` and `selected_market_probability` for every pick.
4. Cached `prediction_log.csv` files with an older header are automatically rewritten with the new canonical header before appending new rows.
5. Database picks are filtered by `SHADOW_COMPARE_SINCE_UTC` using `last_seen_at`/`original_created_at`, so a new validation window can exclude old records without cleaning Supabase.

## New model metadata

- `MODEL_VERSION = V25.1.2c-shadow-compare-cache-normalization`
- `CONFIG_VERSION = 2026-07-01-v25.1.2c-shadow-compare-hardening`
- `FEATURE_SET_VERSION = v25.1.2c-compare-cache-normalization`
- `CALIBRATION_VERSION = v25.0.9-candidate-weights`

## Validation

- `python -m compileall football_agent -q` — OK
- `python smoke_test.py` — OK
- `python -m unittest discover -s tests` — OK, 94 tests passed
