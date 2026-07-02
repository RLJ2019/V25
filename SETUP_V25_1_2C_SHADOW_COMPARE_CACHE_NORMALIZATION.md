# Setup V25.1.2c

## Installation

Upload/replace the repository files with the V25.1.2c build on the active GitHub repository.

## Important after installation

Set a fresh compare window after the V25.1.2c deployment, for example:

```env
SHADOW_COMPARE_SINCE_UTC=<UTC time after V25.1.2c upload, before the next daily run>
```

This avoids comparing older V25.1.2b identities with new V25.1.2c identities.

Supabase cleanup is not required if `SHADOW_COMPARE_SINCE_UTC` is moved to a fresh time after deployment. V25.1.2c filters database rows by `last_seen_at`/`original_created_at`.

## Recommended validation order

1. Run `healthcheck`
2. Run `database_healthcheck`
3. Run `daily`
4. Run `compare_shadow`

Expected compare result:

```json
{
  "status": "PASS",
  "missing_in_database": [],
  "unexpected_in_database": [],
  "numeric_mismatches": [],
  "critical_errors": 0,
  "shadow_parity_percent": 100.0
}
```

## Do not change

Do not change staking, odds discovery, decision logic, or database schema as part of this hotfix.
