from __future__ import annotations

import unittest

from football_agent.scripts.compare_shadow_state import (
    _critical_count,
    _filter_state_to_eligible_keys,
)
from football_agent.storage.model_versions import (
    CALIBRATION_VERSION,
    CONFIG_VERSION,
    FEATURE_SET_VERSION,
    MODEL_VERSION,
)


class TestV2512dZeroWindowStateGuard(unittest.TestCase):
    def test_empty_eligible_state_keys_filters_all_cached_notification_state(self):
        cached_state = {
            "af-old|NONE|NONE": {"status": "sent"},
            "af-other|OVER_UNDER_2_5|OVER_2_5": {"status": "sent"},
        }
        self.assertEqual(_filter_state_to_eligible_keys(cached_state, set()), {})

    def test_non_empty_eligible_state_keys_keep_only_current_window(self):
        cached_state = {
            "af-1|NONE|NONE": {"status": "sent"},
            "af-old|NONE|NONE": {"status": "sent"},
        }
        filtered = _filter_state_to_eligible_keys(cached_state, {"af-1|NONE|NONE"})
        self.assertEqual(set(filtered), {"af-1|NONE|NONE"})

    def test_zero_pick_window_cached_state_is_not_critical(self):
        report = {
            "missing_in_database": [],
            "unexpected_in_database": [],
            "database_duplicate_identities": [],
            "state_missing_in_database": [],
            "state_unexpected_in_database": [],
            "state_mismatches": [],
            "numeric_mismatches": [],
        }
        self.assertEqual(_critical_count(report), 0)

    def test_v2512d_metadata_versions(self):
        self.assertEqual(MODEL_VERSION, "V25.1.2d-shadow-compare-zero-window-state-guard")
        self.assertEqual(CONFIG_VERSION, "2026-07-02-v25.1.2d-shadow-compare-zero-window")
        self.assertEqual(FEATURE_SET_VERSION, "v25.1.2d-zero-window-state-guard")
        self.assertEqual(CALIBRATION_VERSION, "v25.0.9-candidate-weights")


if __name__ == "__main__":
    unittest.main()
