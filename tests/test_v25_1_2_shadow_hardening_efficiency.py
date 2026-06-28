from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from football_agent.data.api_football import ApiFootballClient
from football_agent.data.odds import BookmakerProfiler, OddsDiscoveryService
from football_agent.decision.staking import FractionalKellyStaking
from football_agent.scripts.compare_shadow_state import _critical_count, _numeric_mismatches
from football_agent.scripts.run_daily import _is_lineup_monitor_runtime
from football_agent.schemas import Competition, Fixture


def _fixture(api_id: int, day_offset: int, competition_key: str = "eredivisie") -> Fixture:
    kickoff = (datetime.now(timezone.utc) + timedelta(days=day_offset)).replace(microsecond=0).isoformat()
    return Fixture(
        id=f"af-{api_id}",
        competition_key=competition_key,
        competition_name="Eredivisie",
        home_team=f"Home {api_id}",
        away_team=f"Away {api_id}",
        kickoff_utc=kickoff,
        source="api-football",
        api_football_fixture_id=api_id,
    )


class FakeLeagueBulkOddsClient:
    enabled = True

    def __init__(self):
        self.parser = ApiFootballClient(api_key="test")
        self.calls = []

    def odds_bulk(self, *, league_id: int, season: int, odds_date=None, page: int = 1, **kwargs):
        self.calls.append({"league_id": league_id, "season": season, "odds_date": odds_date, "page": page})
        return {
            "results": 1,
            "paging": {"current": 1, "total": 1},
            "response": [
                {
                    "fixture": {"id": 2002},
                    "update": "2026-06-28T12:00:00Z",
                    "bookmakers": [
                        {
                            "name": "Bet365",
                            "bets": [
                                {"name": "Match Winner", "values": [
                                    {"value": "Home", "odd": "2.00"},
                                    {"value": "Draw", "odd": "3.20"},
                                    {"value": "Away", "odd": "3.80"},
                                ]}
                            ],
                        }
                    ],
                }
            ],
        }

    def parse_odds_response(self, data):
        return self.parser.parse_odds_response(data)


class V2512ShadowHardeningEfficiencyTests(unittest.TestCase):
    def test_odds_discovery_groups_by_league_not_by_date(self):
        fixtures = [_fixture(2001, 1), _fixture(2002, 2), _fixture(2003, 3)]
        comp = Competition(
            key="eredivisie",
            name="Eredivisie",
            country="Netherlands",
            type="league",
            football_data_code="DED",
            api_football_league_id=88,
        )
        client = FakeLeagueBulkOddsClient()
        service = OddsDiscoveryService(
            client,
            BookmakerProfiler(profiles={}),
            discovery_window_days=14,
            max_pages_per_query=2,
            max_requests=10,
        )
        result = service.discover(fixtures, {"eredivisie": comp}, season=2026)

        self.assertEqual(result.metrics.bulk_queries, 1)
        self.assertEqual(result.metrics.odds_requests, 1)
        self.assertEqual(client.calls, [{"league_id": 88, "season": 2026, "odds_date": None, "page": 1}])
        self.assertEqual(result.metrics.fixtures_with_odds, 1)
        self.assertEqual(result.metrics.odds_rows_discovered, 3)

    def test_lineup_monitor_runtime_forces_realtime_odds_path(self):
        self.assertTrue(_is_lineup_monitor_runtime("lineup_monitor", False))
        self.assertTrue(_is_lineup_monitor_runtime("lineup-monitor", False))
        self.assertTrue(_is_lineup_monitor_runtime("daily", True))
        self.assertFalse(_is_lineup_monitor_runtime("daily", False))

    def test_longshot_kelly_deflator_is_applied_before_unit_clamp(self):
        staking = FractionalKellyStaking(
            kelly_fraction=0.25,
            bankroll_units=100,
            max_units_per_pick=100,
            min_units_for_value=0.0,
        )
        rec = staking.recommend(
            model_probability=0.20,
            decimal_odds=8.00,
            uncertainty_score=2.0,
            data_quality=9.0,
            confidence=9.0,
        )
        b = 7.0
        raw = ((b * 0.20) - 0.80) / b
        uncertainty_component = 1.0 - (2.0 / 10.0)
        quality_component = (9.0 + 9.0) / 20.0
        risk_multiplier = (0.65 * uncertainty_component) + (0.35 * quality_component)
        expected_fractional = raw * 0.25 * risk_multiplier * 0.5
        self.assertAlmostEqual(rec.raw_kelly_fraction, raw, places=6)
        self.assertAlmostEqual(rec.fractional_kelly, expected_fractional, places=6)
        self.assertIn("longshot deflator 0.50x", rec.reason)

    def test_shadow_numeric_mismatch_counts_as_critical(self):
        local_rows = {
            "fx|1X2|HOME|v": {
                "selection": "HOME",
                "odds": "2.000",
                "model_home": "0.600000",
                "market_home": "0.510000",
                "expected_value": "0.200000",
                "probability_edge": "0.090000",
                "stake_units": "1.000",
            }
        }
        database_rows = {
            "fx|1X2|HOME|v": {
                "entry_odds": 2.05,
                "model_probability": 0.60,
                "market_probability": 0.51,
                "expected_value": 0.20,
                "probability_edge": 0.09,
                "stake_units": 1.0,
            }
        }
        mismatches = _numeric_mismatches(local_rows, database_rows)
        self.assertEqual(len(mismatches), 1)
        report = {"numeric_mismatches": mismatches}
        self.assertEqual(_critical_count(report), 1)


if __name__ == "__main__":
    unittest.main()
