# Setup – V25.1.2e Stale NO_BET Notification State Guard

## Purpose

This ZIP is a compare-only hotfix for the active V25.1.2d shadow validation.

It is intended to fix false FAILs caused by old cached local `notification_state.json` rows that are:

- older than `SHADOW_COMPARE_SINCE_UTC`
- `status = NO_BET`
- `sent = false`

## Upload target

Upload to:

```text
RLJ2019/V25
branch: main
```

Only do this if the latest compare failed solely because of stale local NO_BET notification state and pick parity was 100%.

## Do not change

Do not change:

- Supabase data
- GitHub variables
- secrets
- workflows
- database schema
- V25.1.3 dev branch

## After upload

Run only:

```text
Actions → Daily V25 Multi-League Agent → Run workflow
branch: main
mode: compare_shadow
```

Expected result:

```text
status: PASS
critical_errors: 0
shadow_parity_percent: 100.0
state_missing_in_database: []
```

If it passes, the 2026-07-06 daily run can be accepted as the fifth valid shadow validation day, provided the daily run itself was green and `scanned > 0`.
