from __future__ import annotations

import os
from datetime import date
from typing import List, Dict, Any, Optional
from .http import HttpClient
from football_agent.schemas import Fixture, Competition
from football_agent.models.motivation_model import StandingRow


class FootballDataClient:
    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self, api_key: Optional[str] = None, http: Optional[HttpClient] = None):
        self.api_key = api_key or os.getenv("FOOTBALL_DATA_API_KEY")
        self.http = http or HttpClient()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise RuntimeError("FOOTBALL_DATA_API_KEY ontbreekt.")
        return {"X-Auth-Token": self.api_key}

    def matches(self, competition: Competition, date_from: date, date_to: date) -> List[Fixture]:
        if not competition.football_data_code:
            return []
        data = self.http.get_json(
            f"{self.BASE_URL}/competitions/{competition.football_data_code}/matches",
            headers=self._headers(),
            params={"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()},
        )
        fixtures: List[Fixture] = []
        for m in data.get("matches", []):
            score = m.get("score", {}).get("fullTime", {}) or {}
            fixture_id = str(m.get("id"))
            fixtures.append(
                Fixture(
                    id=f"fd-{fixture_id}",
                    competition_key=competition.key,
                    competition_name=competition.name,
                    home_team=(m.get("homeTeam") or {}).get("name", "Unknown home"),
                    away_team=(m.get("awayTeam") or {}).get("name", "Unknown away"),
                    kickoff_utc=m.get("utcDate", ""),
                    status=m.get("status", "SCHEDULED"),
                    home_score=score.get("home"),
                    away_score=score.get("away"),
                    source="football-data.org",
                    football_data_match_id=m.get("id"),
                )
            )
        return fixtures

    def standings(self, competition: Competition) -> Dict[str, Any]:
        if not competition.football_data_code:
            return {}
        return self.http.get_json(
            f"{self.BASE_URL}/competitions/{competition.football_data_code}/standings",
            headers=self._headers(),
        )

    def standings_table(self, competition: Competition) -> List[StandingRow]:
        """Return normalized standings rows usable by MotivationModel."""
        data = self.standings(competition)
        tables = data.get("standings", []) or []
        # Prefer TOTAL table. football-data may also expose HOME/AWAY tables.
        selected = None
        for table in tables:
            if str(table.get("type", "")).upper() == "TOTAL":
                selected = table
                break
        selected = selected or (tables[0] if tables else {})
        rows: List[StandingRow] = []
        for item in selected.get("table", []) or []:
            team = item.get("team") or {}
            rows.append(
                StandingRow(
                    team_name=str(team.get("name") or team.get("shortName") or "Unknown"),
                    position=int(item.get("position") or 0),
                    points=int(item.get("points") or 0),
                    played=int(item.get("playedGames") or item.get("played") or 0),
                    goal_difference=int(item.get("goalDifference") or 0),
                )
            )
        return [r for r in rows if r.position > 0 and r.team_name != "Unknown"]

