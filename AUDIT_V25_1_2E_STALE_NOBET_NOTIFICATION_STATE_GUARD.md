# V25.1.2e – Stale NO_BET Notification State Guard

## Scope

This is a compare-only hotfix for `football_agent/scripts/compare_shadow_state.py`.

It does **not** change:

- pick selection
- model scoring
- odds discovery
- staking
- database write schema
- settlement logic
- Supabase migrations

`MODEL_VERSION` is intentionally preserved as `V25.1.2d-shadow-compare-zero-window-state-guard` to avoid pick identity drift during the active shadow validation window.

## Problem

During the 2026-07-06 shadow compare, pick parity was perfect:

- local unique picks matched database unique picks
- no missing picks
- no unexpected database picks
- no numeric mismatches
- shadow parity = 100%

The run failed only because an old cached local `notification_state.json` row existed for:

```text
af-1554373|NONE|NONE
```

That row was:

- `status = NO_BET`
- `sent = false`
- `updated_at_utc = 2026-06-29T17:14:13Z`
- older than `SHADOW_COMPARE_SINCE_UTC = 2026-07-02T12:30:00Z`

The row represented old local notification hygiene, not active shadow database parity.

## Fix

V25.1.2e filters stale local notification-state rows before state comparison when all these conditions are true:

```text
updated_at_utc < SHADOW_COMPARE_SINCE_UTC
status == NO_BET
sent == false
```

These stale local NO_BET rows no longer produce a critical `state_missing_in_database` error.

Current/local states inside the compare window are still compared normally.
Sent states are still compared normally.
Non-NO_BET states are still compared normally.

## Validation

Local validation:

```text
compileall OK
102 unit tests passed
```

New tests:

- `test_stale_unsent_no_bet_state_before_compare_since_is_ignored`
- `test_current_unsent_no_bet_state_is_kept`
- `test_sent_or_non_no_bet_states_are_not_filtered`
- `test_model_identity_version_is_intentionally_preserved`

## Operational instruction

Apply this hotfix only to `main` if the active V25.1.2d shadow compare fails solely on stale unsent NO_BET notification-state cache while pick parity remains 100%.

After upload:

1. Run `compare_shadow` on `main`.
2. Do not run Supabase clean.
3. Do not change variables.
4. Do not run migrations.
5. Keep V25.1.3 parked on dev until shadow validation is complete.
