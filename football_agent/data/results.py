from __future__ import annotations

from typing import Any, Mapping, Optional

from football_agent.data.api_football import ApiFootballClient
from football_agent.settlement.base import FixtureResult


def _api_fixture_id(fixture_id: str | int | None) -> Optional[int]:
    if fixture_id is None:
        return None
    raw = str(fixture_id)
    if raw.startswith("af-"):
        raw = raw[3:]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class FixtureResultProvider:
    def __init__(self, api_client: Optional[ApiFootballClient] = None):
        self.api_client = api_client or ApiFootballClient()

    @staticmethod
    def _from_api_item(item: Mapping[str, Any], fallback_fixture_id: str) -> FixtureResult:
        fixture = item.get("fixture", {}) or {}
        status = fixture.get("status", {}) or {}
        goals = item.get("goals", {}) or {}
        f_id = fixture.get("id") or fallback_fixture_id
        return FixtureResult(
            fixture_id=f"af-{f_id}" if str(f_id).isdigit() else str(f_id),
            status_short=str(status.get("short") or status.get("long") or ""),
            status_long=str(status.get("long") or status.get("short") or ""),
            kickoff_utc=fixture.get("date"),
            home_score=goals.get("home"),
            away_score=goals.get("away"),
            elapsed=status.get("elapsed"),
            source="api-football",
        )

    @staticmethod
    def _from_fixture_row(fixture_id: str, fixture_row: Optional[Mapping[str, Any]]) -> Optional[FixtureResult]:
        if not fixture_row:
            return None
        return FixtureResult(
            fixture_id=fixture_id,
            status_short=str(fixture_row.get("status") or ""),
            status_long=str(fixture_row.get("status") or ""),
            kickoff_utc=fixture_row.get("kickoff_utc"),
            home_score=fixture_row.get("home_score"),
            away_score=fixture_row.get("away_score"),
            source=str(fixture_row.get("source") or "supabase-fixtures"),
        )

    def get_fixture_result(self, fixture_id: str, *, fixture_row: Optional[Mapping[str, Any]] = None) -> Optional[FixtureResult]:
        api_id = _api_fixture_id(fixture_id)
        if self.api_client.enabled and api_id is not None:
            data = self.api_client._get("fixtures", {"id": api_id})
            response = data.get("response", []) or []
            if response:
                return self._from_api_item(response[0], fixture_id)
        return self._from_fixture_row(fixture_id, fixture_row)
