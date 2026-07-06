from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from football_agent.scripts.compare_shadow_state import (
    _critical_count,
    _local_pick_identities,
    _local_state,
    _numeric_mismatches,
    _state_keys_from_identities,
)
from football_agent.storage.model_versions import (
    CALIBRATION_VERSION,
    CONFIG_VERSION,
    FEATURE_SET_VERSION,
    MODEL_VERSION,
)
from football_agent.storage.prediction_log import PredictionLog


class TestV2512cShadowCompareCacheNormalization(unittest.TestCase):
    def test_selected_probability_columns_fix_non_1x2_value_pick_compare(self):
        local_rows = {
            "af-1|OVER_UNDER_2_5|OVER_2_5|v": {
                "fixture_id": "af-1",
                "market": "OVER_UNDER_2_5",
                "selection": "OVER_2_5",
                "selected_model_probability": "0.43550060",
                "selected_market_probability": "0.00000000",
                "odds": "2.300",
                "expected_value": "0.001651",
                "probability_edge": "0.435501",
                "stake_units": "0.250",
            }
        }
        database_rows = {
            "af-1|OVER_UNDER_2_5|OVER_2_5|v": {
                "entry_odds": 2.3,
                "model_probability": 0.4355006,
                "market_probability": 0.0,
                "expected_value": 0.001651,
                "probability_edge": 0.435501,
                "stake_units": 0.25,
            }
        }

        self.assertEqual(_numeric_mismatches(local_rows, database_rows), [])

    def test_missing_selected_probability_for_non_1x2_still_fails(self):
        local_rows = {
            "af-1|OVER_UNDER_2_5|OVER_2_5|v": {
                "fixture_id": "af-1",
                "market": "OVER_UNDER_2_5",
                "selection": "OVER_2_5",
                "odds": "2.300",
                "expected_value": "0.001651",
                "probability_edge": "0.435501",
                "stake_units": "0.250",
            }
        }
        database_rows = {
            "af-1|OVER_UNDER_2_5|OVER_2_5|v": {
                "entry_odds": 2.3,
                "model_probability": 0.4355006,
                "market_probability": 0.0,
                "expected_value": 0.001651,
                "probability_edge": 0.435501,
                "stake_units": 0.25,
            }
        }

        fields = {item["field"] for item in _numeric_mismatches(local_rows, database_rows)}
        self.assertEqual(fields, {"model_probability", "market_probability"})

    def test_local_duplicate_identities_are_reported_but_not_critical(self):
        report = {
            "missing_in_database": [],
            "unexpected_in_database": [],
            "local_duplicate_identities": ["fx|NONE|NONE|v"],
            "database_duplicate_identities": [],
            "state_missing_in_database": [],
            "state_unexpected_in_database": [],
            "state_mismatches": [],
            "numeric_mismatches": [],
        }
        self.assertEqual(_critical_count(report), 0)

    def test_local_pick_identity_dedup_keeps_newest_most_complete_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prediction_log.csv"
            fieldnames = [
                "created_at_utc", "fixture_id", "market", "selection", "model_version",
                "selected_model_probability", "selected_market_probability", "odds",
            ]
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow({
                    "created_at_utc": "2026-07-01T21:00:01Z",
                    "fixture_id": "af-1",
                    "market": "OVER_UNDER_2_5",
                    "selection": "OVER_2_5",
                    "model_version": "v",
                    "odds": "2.300",
                })
                writer.writerow({
                    "created_at_utc": "2026-07-01T21:00:02Z",
                    "fixture_id": "af-1",
                    "market": "OVER_UNDER_2_5",
                    "selection": "OVER_2_5",
                    "model_version": "v",
                    "selected_model_probability": "0.43550060",
                    "selected_market_probability": "0.00000000",
                    "odds": "2.300",
                })

            ids, rows = _local_pick_identities(path, "2026-07-01T21:00:00Z")
            identity = "af-1|OVER_UNDER_2_5|OVER_2_5|v"
            self.assertEqual(ids.count(identity), 2)
            self.assertEqual(rows[identity]["selected_model_probability"], "0.43550060")

    def test_notification_state_can_be_filtered_to_current_pick_identities(self):
        eligible = _state_keys_from_identities({
            "af-1|NONE|NONE|v",
            "af-2|OVER_UNDER_2_5|OVER_2_5|v",
        })
        self.assertEqual(eligible, {"af-1|NONE|NONE", "af-2|OVER_UNDER_2_5|OVER_2_5"})
        state_payload = {
            "picks": {
                "a": {"fixture_id": "af-1", "selection": "NONE", "signature": "NO_BET|NONE|NONE|0|0||0|False|FUTURE"},
                "b": {"fixture_id": "af-old", "selection": "NONE", "signature": "NO_BET|NONE|NONE|0|0||0|False|FUTURE"},
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notification_state.json"
            path.write_text(json.dumps(state_payload), encoding="utf-8")
            state = _local_state(path)
            filtered = {key: value for key, value in state.items() if key in eligible}
        self.assertEqual(set(filtered), {"af-1|NONE|NONE"})

    def test_prediction_log_header_migration_adds_selected_probability_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prediction_log.csv"
            old_fields = ["created_at_utc", "fixture_id", "market", "selection", "model_version"]
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=old_fields)
                writer.writeheader()
                writer.writerow({
                    "created_at_utc": "2026-07-01T21:00:01Z",
                    "fixture_id": "af-1",
                    "market": "NONE",
                    "selection": "NONE",
                    "model_version": "v",
                })
            PredictionLog(path).append([])
            with path.open("r", newline="", encoding="utf-8") as f:
                header = next(csv.reader(f))
        self.assertIn("selected_model_probability", header)
        self.assertIn("selected_market_probability", header)

    def test_v2512c_calibration_version_preserved_after_followup_hotfixes(self):
        self.assertEqual(CALIBRATION_VERSION, "v25.0.9-candidate-weights")


if __name__ == "__main__":
    unittest.main()
