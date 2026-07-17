# Setup V25.1.3 Settlement Pipeline

1. Create branch from current stable main:

```bash
git checkout -b dev/v25.1.3-settlement-pipeline
```

2. Upload this ZIP to that branch only.

3. Do not run `supabase/migrations/003_v25_1_3_settlements_hardening.sql` on the live/main Supabase project until V25.1.2d has completed 5/5 valid shadow days. For earlier testing, use a separate test Supabase project.

4. Recommended settlement env vars:

```env
POSTPONED_VOID_AFTER_HOURS=36
SUPPORTED_TOTAL_LINES_MODE=WHOLE_AND_HALF_ONLY
CLV_ALLOW_BENCHMARK_FALLBACK=true
CLV_BENCHMARK_BOOKMAKER_PRIORITY=pinnacle,Pinnacle
CLV_ALLOW_CONSENSUS_FALLBACK=true
CLV_MIN_COMPLETE_BOOKMAKERS_FOR_CONSENSUS=2
```

5. First runs should be:

```text
mode: healthcheck
mode: dry_run
```

Only use `mode: settle` after schema migration and dry-run validation.
