from __future__ import annotations

import unittest
from pathlib import Path

from football_agent.scripts.compare_shadow_state import _numeric_mismatches
from football_agent.storage.model_versions import (
    CALIBRATION_VERSION,
    CONFIG_VERSION,
    FEATURE_SET_VERSION,
    MODEL_VERSION,
)


class TestV2512bTestIsolationNormalization(unittest.TestCase):
    def test_no_bet_empty_local_probability_matches_database_zero(self):
        local_rows = {
            "fx|NONE|NONE|v": {
                "fixture_id": "fx",
                "market": "NONE",
                "selection": "NONE",
                "odds": "",
                "model_home": "",
                "market_home": "",
                "expected_value": "",
                "probability_edge": "",
                "stake_units": "0",
            }
        }
        database_rows = {
            "fx|NONE|NONE|v": {
                "entry_odds": None,
                "model_probability": 0.0,
                "market_probability": 0.0,
                "expected_value": None,
                "probability_edge": None,
                "stake_units": 0.0,
            }
        }

        self.assertEqual(_numeric_mismatches(local_rows, database_rows), [])

    def test_no_bet_normalization_does_not_hide_real_probability_mismatch(self):
        local_rows = {
            "fx|1X2|HOME|v": {
                "fixture_id": "fx",
                "market": "1X2",
                "selection": "HOME",
                "odds": "2.00",
                "model_home": "",
                "market_home": "",
                "expected_value": "",
                "probability_edge": "",
                "stake_units": "0",
            }
        }
        database_rows = {
            "fx|1X2|HOME|v": {
                "entry_odds": 2.0,
                "model_probability": 0.0,
                "market_probability": 0.0,
                "expected_value": None,
                "probability_edge": None,
                "stake_units": 0.0,
            }
        }

        mismatches = _numeric_mismatches(local_rows, database_rows)
        fields = {item["field"] for item in mismatches}
        self.assertIn("model_probability", fields)
        self.assertIn("market_probability", fields)

    def test_daily_workflow_test_step_disables_supabase(self):
        text = Path(".github/workflows/daily-v25-agent-fixed.yml").read_text(encoding="utf-8")
        self.assertIn('- name: Run tests', text)
        self.assertIn('DATABASE_ENABLED: "false"', text)
        self.assertIn('SUPABASE_URL: ""', text)
        self.assertIn('SUPABASE_SECRET_KEY: ""', text)

    def test_weekly_workflow_test_step_disables_supabase(self):
        text = Path(".github/workflows/weekly-v25-recalibration.yml").read_text(encoding="utf-8")
        self.assertIn('- name: Tests', text)
        self.assertIn('DATABASE_ENABLED: "false"', text)
        self.assertIn('SUPABASE_URL: ""', text)
        self.assertIn('SUPABASE_SECRET_KEY: ""', text)

    def test_v2512b_metadata_versions(self):
        self.assertEqual(MODEL_VERSION, "V25.1.2b-test-isolation-normalization")
        self.assertEqual(CONFIG_VERSION, "2026-06-28-v25.1.2b-hardening")
        self.assertEqual(FEATURE_SET_VERSION, "v25.1.2b-test-isolation")
        self.assertEqual(CALIBRATION_VERSION, "v25.0.9-candidate-weights")


if __name__ == "__main__":
    unittest.main()
