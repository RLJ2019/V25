-- V25.1.2b clean shadow-state reset before restarting validation.
-- This keeps table structure and deletes accumulated shadow/test rows.

TRUNCATE TABLE
  pick_events,
  notification_state_shadow,
  odds_snapshots,
  picks,
  fixtures
CASCADE;

NOTIFY pgrst, 'reload schema';
