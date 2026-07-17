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


    def test_only_full_match_btts_market_is_supported(self):
        parser = ApiFootballClient(api_key="test")

        self.assertEqual(
            parser._parse_market_value("Both Teams Score", "Yes"),
            ("BTTS", "BTTS_YES"),
        )
        self.assertEqual(
            parser._parse_market_value("Both Teams Score", "No"),
            ("BTTS", "BTTS_NO"),
        )

        unsupported_markets = (
            "Both Teams Score - First Half",
            "Both Teams To Score - Second Half",
            "Both Teams To Score in Both Halves",
        )

        for bet_name in unsupported_markets:
            with self.subTest(bet_name=bet_name, label="Yes"):
                self.assertEqual(
                    parser._parse_market_value(bet_name, "Yes"),
                    (None, None),
                )

            with self.subTest(bet_name=bet_name, label="No"):
                self.assertEqual(
                    parser._parse_market_value(bet_name, "No"),
                    (None, None),
                )

    def test_odds_response_excludes_non_full_match_btts_variants(self):
        parser = ApiFootballClient(api_key="test")
        data = {
            "response": [
                {
                    "fixture": {"id": 1554386},
                    "update": "2026-07-15T18:00:07+00:00",
                    "bookmakers": [
                        {
                            "name": "Marathonbet",
                            "bets": [
                                {
                                    "id": 8,
                                    "name": "Both Teams Score",
                                    "values": [
                                        {"value": "Yes", "odd": "1.67"},
                                        {"value": "No", "odd": "2.05"},
                                    ],
                                },
                                {
                                    "id": 34,
                                    "name": "Both Teams Score - First Half",
                                    "values": [
                                        {"value": "Yes", "odd": "3.96"},
                                        {"value": "No", "odd": "1.20"},
                                    ],
                                },
                                {
                                    "id": 35,
                                    "name": "Both Teams To Score - Second Half",
                                    "values": [
                                        {"value": "Yes", "odd": "3.04"},
                                        {"value": "No", "odd": "1.32"},
                                    ],
                                },
                                {
                                    "id": 113,
                                    "name": "Both Teams To Score in Both Halves",
                                    "values": [
                                        {"value": "Yes", "odd": "11.00"},
                                        {"value": "No", "odd": "1.00"},
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        parsed = parser.parse_odds_response(data)
        snapshots = parsed[1554386]

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(
            [(row.market, row.selection, row.odds) for row in snapshots],
            [
                ("BTTS", "BTTS_YES", 1.67),
                ("BTTS", "BTTS_NO", 2.05),
            ],
        )


    def test_only_full_match_totals_market_is_supported(self):
        parser = ApiFootballClient(api_key="test")

        self.assertEqual(
            parser._parse_market_value(
                "Goals Over/Under",
                "Over 2.5",
            ),
            ("OVER_UNDER_2_5", "OVER_2_5"),
        )
        self.assertEqual(
            parser._parse_market_value(
                "Goals Over/Under",
                "Under 2.5",
            ),
            ("OVER_UNDER_2_5", "UNDER_2_5"),
        )

        unsupported_markets = (
            "Goals Over/Under First Half",
            "Goals Over/Under - Second Half",
        )

        for bet_name in unsupported_markets:
            with self.subTest(bet_name=bet_name, label="Over 2.5"):
                self.assertEqual(
                    parser._parse_market_value(
                        bet_name,
                        "Over 2.5",
                    ),
                    (None, None),
                )

            with self.subTest(bet_name=bet_name, label="Under 2.5"):
                self.assertEqual(
                    parser._parse_market_value(
                        bet_name,
                        "Under 2.5",
                    ),
                    (None, None),
                )

    def test_odds_response_excludes_non_full_match_totals_variants(self):
        parser = ApiFootballClient(api_key="test")
        data = {
            "response": [
                {
                    "fixture": {"id": 1554386},
                    "update": "2026-07-15T18:00:07+00:00",
                    "bookmakers": [
                        {
                            "name": "Marathonbet",
                            "bets": [
                                {
                                    "id": 5,
                                    "name": "Goals Over/Under",
                                    "values": [
                                        {
                                            "value": "Over 2.5",
                                            "odd": "1.90",
                                        },
                                        {
                                            "value": "Under 2.5",
                                            "odd": "1.90",
                                        },
                                    ],
                                },
                                {
                                    "id": 6,
                                    "name": "Goals Over/Under First Half",
                                    "values": [
                                        {
                                            "value": "Over 2.5",
                                            "odd": "7.50",
                                        },
                                        {
                                            "value": "Under 2.5",
                                            "odd": "1.05",
                                        },
                                    ],
                                },
                                {
                                    "id": 26,
                                    "name": "Goals Over/Under - Second Half",
                                    "values": [
                                        {
                                            "value": "Over 2.5",
                                            "odd": "4.50",
                                        },
                                        {
                                            "value": "Under 2.5",
                                            "odd": "1.18",
                                        },
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ]
        }

        parsed = parser.parse_odds_response(data)
        snapshots = parsed[1554386]

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(
            [
                (row.market, row.selection, row.odds)
                for row in snapshots
            ],
            [
                ("OVER_UNDER_2_5", "OVER_2_5", 1.90),
                ("OVER_UNDER_2_5", "UNDER_2_5", 1.90),
            ],
        )


if __name__ == "__main__":
    unittest.main()
