# V25.1.3 Dev Starter – Settlement Pipeline Migration

This ZIP is based on the stable V25.1.2d shadow baseline and adds the first V25.1.3 dev artifact:

`supabase/migrations/003_v25_1_3_settlements_hardening.sql`

## Important

Do not run this migration on the live/main Supabase project while V25.1.2d is still collecting the 5 valid shadow days.

Recommended flow:

1. Keep `main` frozen on V25.1.2d.
2. Create/use branch: `dev/v25.1.3-settlement-pipeline`.
3. Add this migration file on that dev branch.
4. Build V25.1.3 settlement logic on dev only.
5. Run the migration only after V25.1.2d reaches 5/5 valid shadow days, or run it first on a separate test Supabase project.

## Current settlements table compatibility

The existing table already has:

- `settlement_id` bigint primary key
- `pick_id` uuid not null
- `UNIQUE(pick_id)` via `settlements_pick_id_key`
- `profit_units`
- `closing_odds`
- `clv_odds`
- `clv_probability`
- `settlement_details` jsonb
- `settled_at`

The migration only extends the table with audit, CLV method, settlement basis, and policy fields.
