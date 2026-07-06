from __future__ import annotations

import unittest

from football_agent.scripts.compare_shadow_state import (
    _filter_stale_unsent_no_bet_state,
    _is_stale_unsent_no_bet_state,
)
from football_agent.storage.model_versions import CALIBRATION_VERSION, MODEL_VERSION


class TestV2512eStaleNoBetNotificationStateGuard(unittest.TestCase):
    def test_stale_unsent_no_bet_state_before_compare_since_is_ignored(self):
        state = {
            "af-1554373|NONE|NONE": {
                "status": "NO_BET",
                "sent": False,
                "updated_at_utc": "2026-06-29T17:14:13Z",
            },
            "af-current|NONE|NONE": {
                "status": "NO_BET",
                "sent": False,
                "updated_at_utc": "2026-07-06T14:10:42Z",
            },
        }
        filtered = _filter_stale_unsent_no_bet_state(state, "2026-07-02T12:30:00Z")
        self.assertNotIn("af-1554373|NONE|NONE", filtered)
        self.assertIn("af-current|NONE|NONE", filtered)

    def test_current_unsent_no_bet_state_is_kept(self):
        item = {
            "status": "NO_BET",
            "sent": False,
            "updated_at_utc": "2026-07-06T14:10:42Z",
        }
        self.assertFalse(_is_stale_unsent_no_bet_state(item, "2026-07-02T12:30:00Z"))

    def test_sent_or_non_no_bet_states_are_not_filtered(self):
        since = "2026-07-02T12:30:00Z"
        self.assertFalse(_is_stale_unsent_no_bet_state({
            "status": "WATCHLIST",
            "sent": False,
            "updated_at_utc": "2026-06-29T17:14:13Z",
        }, since))
        self.assertFalse(_is_stale_unsent_no_bet_state({
            "status": "NO_BET",
            "sent": True,
            "updated_at_utc": "2026-06-29T17:14:13Z",
        }, since))

    def test_model_identity_version_is_intentionally_preserved(self):
        # This is a compare-only hotfix; changing MODEL_VERSION would create pick identity drift.
        self.assertEqual(MODEL_VERSION, "V25.1.2d-shadow-compare-zero-window-state-guard")
        self.assertEqual(CALIBRATION_VERSION, "v25.0.9-candidate-weights")


if __name__ == "__main__":
    unittest.main()
