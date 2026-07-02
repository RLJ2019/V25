import unittest
from datetime import date
from unittest.mock import patch

from football_agent.data.fixtures import FixtureProvider
from football_agent.schemas import Fixture


CONFIG = {
    "season": 2026,
    "competitions": [
        {
            "key": "epl",
            "name": "Premier League",
            "country": "England",
            "type": "league",
            "football_data_code": "PL",
            "api_football_league_id": 39,
        }
    ],
}


class FakeFootballData:
    enabled = True

    def __init__(self):
        self.calls = []

    def matches(self, competition, date_from, date_to):
        self.calls.append((competition.key, date_from, date_to))
        return [
            Fixture(
                id="fd-1",
                competition_key=competition.key,
                competition_name=competition.name,
                home_team="A",
                away_team="B",
                kickoff_utc="2024-09-13T18:00:00Z",
                source="football-data.org",
            )
        ]


class FakeApiFootball:
    enabled = True

    def __init__(self):
        self.calls = []

    def fixtures(self, competition, season, date_from, date_to):
        self.calls.append((competition.key, season, date_from, date_to))
        return [
            Fixture(
                id="af-1",
                competition_key=competition.key,
                competition_name=competition.name,
                home_team="C",
                away_team="D",
                kickoff_utc="2024-09-14T18:00:00Z",
                source="api-football",
            )
        ]


class TestFixtureTestMode(unittest.TestCase):
    def test_historical_api_football_hyphen_alias(self):
        fd = FakeFootballData()
        af = FakeApiFootball()
        env = {
            "FIXTURE_TEST_MODE": "true",
            "FIXTURE_DATE_FROM": "2024-09-01",
            "FIXTURE_DATE_TO": "2024-09-30",
            "FIXTURE_SEASON": "2024",
            "FIXTURE_SOURCE": "api-football",
        }
        with patch("football_agent.data.fixtures.load_competitions", return_value=CONFIG), patch.dict("os.environ", env, clear=False):
            fixtures = FixtureProvider(fd, af).upcoming(days_ahead=7, max_matches=80)
        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0].source, "api-football")
        self.assertEqual(fd.calls, [])
        self.assertEqual(af.calls[0][1], 2024)
        self.assertEqual(af.calls[0][2], date(2024, 9, 1))
        self.assertEqual(af.calls[0][3], date(2024, 9, 30))

    def test_historical_football_data_hyphen_alias(self):
        fd = FakeFootballData()
        af = FakeApiFootball()
        env = {
            "FIXTURE_TEST_MODE": "true",
            "FIXTURE_DATE_FROM": "2024-09-01",
            "FIXTURE_DATE_TO": "2024-09-30",
            "FIXTURE_SEASON": "2024",
            "FIXTURE_SOURCE": "football-data",
        }
        with patch("football_agent.data.fixtures.load_competitions", return_value=CONFIG), patch.dict("os.environ", env, clear=False):
            fixtures = FixtureProvider(fd, af).upcoming()
        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0].source, "football-data.org")
        self.assertEqual(af.calls, [])
        self.assertEqual(fd.calls[0][1], date(2024, 9, 1))

    def test_test_mode_requires_dates(self):
        env = {
            "FIXTURE_TEST_MODE": "true",
            "FIXTURE_DATE_FROM": "",
            "FIXTURE_DATE_TO": "",
        }
        with patch("football_agent.data.fixtures.load_competitions", return_value=CONFIG), patch.dict("os.environ", env, clear=False):
            with self.assertRaises(RuntimeError):
                FixtureProvider(FakeFootballData(), FakeApiFootball()).upcoming()


if __name__ == "__main__":
    unittest.main()
