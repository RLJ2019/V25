from __future__ import annotations

import os
from datetime import date, timedelta
from typing import List, Optional

from football_agent.config.loader import load_competitions
from football_agent.schemas import Competition, Fixture
from .football_data import FootballDataClient
from .api_football import ApiFootballClient


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "ja"}


def _env_date(name: str) -> Optional[date]:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"{name} heeft een ongeldige datum: {value}. "
            "Gebruik formaat YYYY-MM-DD, bijvoorbeeld 2024-09-13."
        ) from exc


def _normalize_source(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        "football_data": "football_data",
        "api_football": "api_football",
        "auto": "auto",
    }
    if normalized not in aliases:
        raise ValueError("FIXTURE_SOURCE moet auto, football-data/football_data of api-football/api_football zijn.")
    return aliases[normalized]


class FixtureProvider:
    def __init__(
        self,
        football_data: FootballDataClient | None = None,
        api_football: ApiFootballClient | None = None,
    ):
        self.football_data = football_data or FootballDataClient()
        self.api_football = api_football or ApiFootballClient()

    def competitions(self) -> List[Competition]:
        raw = load_competitions()
        return [Competition(**c) for c in raw.get("competitions", [])]

    def upcoming(self, days_ahead: int = 7, max_matches: int = 80) -> List[Fixture]:
        config = load_competitions()
        today = date.today()
        configured_season = int(config.get("season", today.year))
        test_mode = _env_bool("FIXTURE_TEST_MODE", False)

        if test_mode:
            date_from = _env_date("FIXTURE_DATE_FROM")
            date_to = _env_date("FIXTURE_DATE_TO")
            if date_from is None or date_to is None:
                raise RuntimeError(
                    "FIXTURE_TEST_MODE staat aan, maar FIXTURE_DATE_FROM of FIXTURE_DATE_TO ontbreekt."
                )
            if date_to < date_from:
                raise RuntimeError("FIXTURE_DATE_TO mag niet vóór FIXTURE_DATE_FROM liggen.")
            season_raw = os.getenv("FIXTURE_SEASON", str(configured_season)).strip()
            try:
                season = int(season_raw)
            except ValueError as exc:
                raise ValueError(f"FIXTURE_SEASON moet een jaartal zijn. Ontvangen: {season_raw}") from exc
            source = _normalize_source(os.getenv("FIXTURE_SOURCE", "api_football"))
            print("Fixture mode: TEST")
        else:
            date_from = today
            date_to = today + timedelta(days=days_ahead)
            season = configured_season
            # V25.1.1: respect FIXTURE_SOURCE in live mode too. The previous live path
            # forced auto, which could pull football-data fixtures without API-Football
            # fixture ids and made odds discovery impossible for those matches.
            source = _normalize_source(os.getenv("FIXTURE_SOURCE", "auto"))
            print("Fixture mode: LIVE")

        print(
            f"Fixture scan: {date_from} t/m {date_to} | season={season} | "
            f"source={source} | days_ahead={days_ahead}"
        )

        fixtures: List[Fixture] = []
        for comp in self.competitions():
            got: List[Fixture] = []
            print(
                f"Scan competitie: {comp.name} | football_data_code={comp.football_data_code} | "
                f"api_football_league_id={comp.api_football_league_id}"
            )
            use_football_data = source in {"auto", "football_data"}
            use_api_football = source in {"auto", "api_football"}

            if use_football_data and self.football_data.enabled and comp.football_data_code:
                try:
                    got = self.football_data.matches(comp, date_from, date_to)
                    print(f"{comp.name}: football-data wedstrijden={len(got)}")
                except Exception as exc:
                    print(f"football-data faalde voor {comp.name}: {exc}")

            if not got and use_api_football and self.api_football.enabled and comp.api_football_league_id:
                try:
                    got = self.api_football.fixtures(comp, season, date_from, date_to)
                    print(f"{comp.name}: api-football wedstrijden={len(got)}")
                except Exception as exc:
                    print(f"api-football faalde voor {comp.name}: {exc}")

            if not got:
                print(f"{comp.name}: geen wedstrijden gevonden binnen deze periode")
            fixtures.extend(got)

        fixtures.sort(key=lambda fixture: fixture.kickoff_utc)
        seen = set()
        unique: List[Fixture] = []
        for fixture in fixtures:
            key = (
                fixture.competition_key,
                fixture.home_team.lower(),
                fixture.away_team.lower(),
                fixture.kickoff_utc[:10],
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(fixture)

        print(f"Fixture scan totaal: raw={len(fixtures)} unique={len(unique)} max={max_matches}")
        return unique[:max_matches]
