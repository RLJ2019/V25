from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from football_agent.data.api_football import ApiFootballClient
from football_agent.data.odds import BookmakerProfiler, OddsDiscoveryService
from football_agent.schemas import Competition, Fixture


def _fixture(api_id: int, day_offset: int = 1) -> Fixture:
    kickoff = (datetime.now(timezone.utc) + timedelta(days=day_offset)).replace(microsecond=0).isoformat()
    return Fixture(
        id=f"af-{api_id}",
        competition_key="champions_league",
        competition_name="Champions League",
        home_team=f"Home {api_id}",
        away_team=f"Away {api_id}",
        kickoff_utc=kickoff,
        source="api-football",
        api_football_fixture_id=api_id,
    )


class FakeBulkOddsClient:
    enabled = True

    def __init__(self):
        self.parser = ApiFootballClient(api_key="test")
        self.calls = []

    def odds_bulk(self, *, league_id: int, season: int, odds_date=None, page: int = 1, **kwargs):
        self.calls.append((league_id, season, odds_date, page))
        return {
            "results": 1,
            "paging": {"current": 1, "total": 1},
            "response": [
                {
                    "fixture": {"id": 1002},
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


class OddsDiscoveryTests(unittest.TestCase):
    def test_bulk_odds_discovery_prioritizes_fixtures_with_odds(self):
        fixtures = [_fixture(1001), _fixture(1002), _fixture(1003)]
        comp = Competition(
            key="champions_league",
            name="Champions League",
            country="Europe",
            type="europe",
            football_data_code="CL",
            api_football_league_id=2,
        )
        service = OddsDiscoveryService(
            FakeBulkOddsClient(),
            BookmakerProfiler(profiles={}),
            discovery_window_days=14,
            max_pages_per_query=2,
            max_requests=10,
        )
        result = service.discover(fixtures, {"champions_league": comp}, season=2026)
        selected, selected_with, selected_without = service.select_with_odds_priority(
            fixtures, result.odds_by_api_fixture_id, max_matches=2
        )

        self.assertEqual(result.metrics.odds_requests, 1)
        self.assertEqual(result.metrics.fixtures_with_odds, 1)
        self.assertEqual(result.metrics.fixtures_without_odds, 2)
        self.assertEqual(result.metrics.odds_rows_discovered, 3)
        self.assertEqual(selected[0].api_football_fixture_id, 1002)
        self.assertEqual(selected_with, 1)
        self.assertEqual(selected_without, 1)


if __name__ == "__main__":
    unittest.main()
