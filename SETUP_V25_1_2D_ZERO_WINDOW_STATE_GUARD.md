# Setup – V25.1.2d

1. Upload/replace repository files with V25.1.2d.
2. Do not clean Supabase unless old external writers polluted it again.
3. Set `SHADOW_COMPARE_SINCE_UTC` to a UTC timestamp just before the new V25.1.2d daily run, not a Dutch local-time timestamp.
4. Run:
   - `mode=healthcheck`
   - `mode=database_healthcheck`
   - `mode=daily`
   - `mode=compare_shadow`

Expected compare output after a daily run:
- `status=PASS`
- `critical_errors=0`
- `missing_in_database=[]`
- `unexpected_in_database=[]`
- `numeric_mismatches=[]`

If compare is run before any daily rows exist in the new window, V25.1.2d should no longer fail because of cached notification-state rows.
