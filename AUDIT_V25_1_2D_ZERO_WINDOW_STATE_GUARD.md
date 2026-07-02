# V25.1.2d – Shadow Compare Zero-Window State Guard

## Reason
V25.1.2c correctly filtered local/database picks by `SHADOW_COMPARE_SINCE_UTC`, but a compare run executed before the new window contained any eligible picks still compared cached `notification_state.json` rows. This produced a false fail with `local_rows=0`, `database_rows=0`, `eligible_notification_state_keys=0`, but stale cached notification states still counted as critical.

## Fix
- Added `_filter_state_to_eligible_keys()`.
- When there are zero eligible pick identities in the compare window, notification state comparison is also an empty set.
- When eligible identities exist, notification states are compared only for those current-window identity keys.
- No prediction logic changed.
- No odds discovery, staking, database schema, or decision logic changed.

## Scope
Shadow-compare hardening only.
