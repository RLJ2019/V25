from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict, List, Mapping, Optional
from .http import HttpClient
from football_agent.schemas import Competition, Fixture, OddsSnapshot


class ApiFootballClient:
    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key: Optional[str] = None, http: Optional[HttpClient] = None):
        self.api_key = api_key or os.getenv("API_FOOTBALL_KEY")
        self.http = http or HttpClient()
        self._disabled_reason: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and self._disabled_reason is None

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise RuntimeError("API_FOOTBALL_KEY ontbreekt.")
        return {"x-apisports-key": self.api_key}

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self._disabled_reason:
            print(f"API-Football overgeslagen: disabled_reason={self._disabled_reason}")
            return {"response": [], "errors": {"disabled": self._disabled_reason}}
        data = self.http.get_json(
            f"{self.BASE_URL}/{endpoint.lstrip('/')}",
            headers=self._headers(),
            params=params,
        )
        errors = data.get("errors")
        response = data.get("response", []) or []
        results = data.get("results")
        if errors:
            print(f"API-Football errors voor endpoint={endpoint} params={params}: {errors}")
        print(
            f"API-Football response endpoint={endpoint} params={params} "
            f"results={results} response_len={len(response)}"
        )
        if isinstance(errors, dict) and errors.get("plan"):
            self._disabled_reason = str(errors.get("plan"))
            print(f"API-Football uitgeschakeld door plan-limit: {self._disabled_reason}")
        return data

    def fixtures(self, competition: Competition, season: int, date_from: date, date_to: date) -> List[Fixture]:
        if not competition.api_football_league_id:
            print(f"API-Football fixtures overgeslagen voor {competition.name}: geen api_football_league_id")
            return []
        if not self.enabled:
            print(f"API-Football fixtures overgeslagen voor {competition.name}: client disabled")
            return []
        print(
            f"API-Football fixtures ophalen voor {competition.name}: "
            f"league={competition.api_football_league_id} season={season} "
            f"from={date_from.isoformat()} to={date_to.isoformat()}"
        )
        data = self._get("fixtures", {
            "league": competition.api_football_league_id,
            "season": season,
            "from": date_from.isoformat(),
            "to": date_to.isoformat(),
        })
        fixtures: List[Fixture] = []
        for item in data.get("response", []) or []:
            fixture = item.get("fixture", {}) or {}
            teams = item.get("teams", {}) or {}
            goals = item.get("goals", {}) or {}
            f_id = fixture.get("id")
            fixtures.append(
                Fixture(
                    id=f"af-{f_id}",
                    competition_key=competition.key,
                    competition_name=competition.name,
                    home_team=(teams.get("home") or {}).get("name", "Unknown home"),
                    away_team=(teams.get("away") or {}).get("name", "Unknown away"),
                    kickoff_utc=(fixture.get("date") or ""),
                    status=(fixture.get("status") or {}).get("long", "SCHEDULED"),
                    venue=(fixture.get("venue") or {}).get("name"),
                    city=(fixture.get("venue") or {}).get("city"),
                    home_score=goals.get("home"),
                    away_score=goals.get("away"),
                    source="api-football",
                    api_football_fixture_id=f_id,
                )
            )
        print(f"API-Football fixtures verwerkt voor {competition.name}: {len(fixtures)} wedstrijden")
        return fixtures

    @staticmethod
    def _parse_market_value(bet_name: str, label: str) -> tuple[str | None, str | None]:
        bet_name = str(bet_name or "").lower()
        label = str(label or "").lower()
        market = None
        selection = None
        if bet_name in {"match winner", "1x2"}:
            market = "1X2"
            selection = "DRAW" if label in {"draw", "x"} else "HOME" if label in {"home", "1"} else "AWAY" if label in {"away", "2"} else None
        elif "over/under" in bet_name or "goals over/under" in bet_name or bet_name in {"goals over/under"}:
            # API-Football commonly labels values as "Over 2.5" / "Under 2.5".
            if "2.5" in label and "over" in label:
                market = "OVER_UNDER_2_5"
                selection = "OVER_2_5"
            elif "2.5" in label and "under" in label:
                market = "OVER_UNDER_2_5"
                selection = "UNDER_2_5"
        elif "both teams" in bet_name or "both teams score" in bet_name:
            market = "BTTS"
            if label in {"yes", "y"}:
                selection = "BTTS_YES"
            elif label in {"no", "n"}:
                selection = "BTTS_NO"
        return market, selection

    def _parse_single_odds_response_item(self, resp: Mapping[str, Any]) -> List[OddsSnapshot]:
        update = resp.get("update") or ""
        snapshots: List[OddsSnapshot] = []
        for bookmaker in resp.get("bookmakers", []) or []:
            b_name = str(bookmaker.get("name", "unknown")).lower().replace(" ", "_")
            for bet in bookmaker.get("bets", []) or []:
                bet_name = str(bet.get("name", ""))
                for val in bet.get("values", []) or []:
                    market, selection = self._parse_market_value(bet_name, str(val.get("value", "")))
                    if not market or not selection:
                        continue
                    try:
                        odd = float(val.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    snapshots.append(OddsSnapshot(bookmaker=b_name, market=market, selection=selection, odds=odd, timestamp_utc=update))
        return snapshots

    def parse_odds_response(self, data: Mapping[str, Any]) -> Dict[int, List[OddsSnapshot]]:
        """Parse API-Football /odds response into fixture-id keyed snapshots.

        Works for both /odds?fixture=... and bulk /odds?league=...&date=... pages.
        Unsupported markets are intentionally ignored; V25.1.1 focuses on 1X2,
        Over/Under 2.5 and BTTS because those are the markets used downstream.
        """
        by_fixture: Dict[int, List[OddsSnapshot]] = {}
        for resp in data.get("response", []) or []:
            fixture_info = resp.get("fixture", {}) or {}
            fixture_id = fixture_info.get("id")
            try:
                fixture_id_int = int(fixture_id)
            except (TypeError, ValueError):
                continue
            snapshots = self._parse_single_odds_response_item(resp)
            if snapshots:
                by_fixture.setdefault(fixture_id_int, []).extend(snapshots)
        return by_fixture

    def odds_bulk(
        self,
        *,
        league_id: int,
        season: int,
        odds_date: Optional[str] = None,
        page: int = 1,
        bookmaker_id: Optional[int] = None,
        bet_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not self.enabled:
            print(f"API-Football bulk odds overgeslagen: client disabled")
            return {"response": [], "results": 0, "paging": {"current": page, "total": 1}}
        params: Dict[str, Any] = {
            "league": int(league_id),
            "season": int(season),
            "page": int(page),
        }
        if odds_date:
            params["date"] = str(odds_date)
        if bookmaker_id is not None:
            params["bookmaker"] = int(bookmaker_id)
        if bet_id is not None:
            params["bet"] = int(bet_id)
        return self._get("odds", params)

    def odds(self, fixture_id: int, bookmaker_ids: Optional[List[int]] = None) -> List[OddsSnapshot]:
        if not self.enabled:
            print(f"API-Football odds overgeslagen voor fixture={fixture_id}: client disabled")
            return []
        params: Dict[str, Any] = {"fixture": fixture_id}
        data = self._get("odds", params)
        by_fixture = self.parse_odds_response(data)
        if by_fixture:
            return list(by_fixture.get(int(fixture_id), []))
        # Defensive fallback for unexpected provider responses without fixture.id.
        snapshots: List[OddsSnapshot] = []
        for resp in data.get("response", []) or []:
            snapshots.extend(self._parse_single_odds_response_item(resp))
        return snapshots

    def injuries(self, fixture_id: int) -> List[Dict[str, Any]]:
        if not self.enabled:
            print(f"API-Football injuries overgeslagen voor fixture={fixture_id}: client disabled")
            return []
        data = self._get("injuries", {"fixture": fixture_id})
        return list(data.get("response", []) or [])

    def lineups(self, fixture_id: int) -> List[Dict[str, Any]]:
        if not self.enabled:
            print(f"API-Football lineups overgeslagen voor fixture={fixture_id}: client disabled")
            return []
        data = self._get("fixtures/lineups", {"fixture": fixture_id})
        return list(data.get("response", []) or [])
