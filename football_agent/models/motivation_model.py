from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
from football_agent.utils import clamp


@dataclass
class StandingRow:
    team_name: str
    position: int
    points: int
    played: int
    goal_difference: int = 0


class MotivationModel:
    """Objective motivation overlay from standings context.

    Motivation is intentionally capped and secondary. It should only encode
    measurable table pressure: title race, European spots, relegation pressure,
    or already-qualified/no-stakes situations.
    """

    def adjustment(
        self,
        must_win: bool = False,
        already_qualified: bool = False,
        relegation_pressure: bool = False,
        title_pressure: bool = False,
    ) -> float:
        adj = 0.0
        if must_win:
            adj += 0.012
        if relegation_pressure:
            adj += 0.008
        if title_pressure:
            adj += 0.006
        if already_qualified:
            adj -= 0.015
        return clamp(adj, -0.025, 0.025)

    def from_standings(
        self,
        team_name: str,
        standings: Optional[List[StandingRow]] = None,
        competition_type: str = "league",
    ) -> float:
        if not standings or competition_type not in {"league", "europe"}:
            return 0.0
        table = sorted(standings, key=lambda r: r.position)
        row = self._find_team(team_name, table)
        if row is None or row.played <= 0:
            return 0.0

        total_teams = len(table)
        if total_teams < 4:
            return 0.0
        leader = table[0]
        # Most leagues play home+away; European league phase differs, but this
        # still gives a conservative remaining-context proxy.
        total_matches = max(row.played, (total_teams - 1) * 2 if competition_type == "league" else 8)
        remaining = max(0, total_matches - row.played)
        late_season = row.played / max(1, total_matches) >= 0.65

        adj = 0.0

        # Title pressure: top teams close enough to still have a realistic race.
        points_from_top = max(0, leader.points - row.points)
        if row.position <= 3 and points_from_top <= max(3, min(9, remaining * 2)):
            adj += 0.006

        # European qualification zone proxy. Works for domestic leagues; low cap.
        euro_cutoff_pos = min(6, total_teams)
        cutoff = self._row_by_position(table, euro_cutoff_pos)
        if cutoff and 3 <= row.position <= min(8, total_teams):
            gap_to_europe = cutoff.points - row.points
            if abs(gap_to_europe) <= max(3, min(7, remaining * 2)):
                adj += 0.004

        # Relegation pressure proxy: bottom 3/4 with small point gaps.
        relegation_line_pos = max(1, total_teams - 3)
        relegation_line = self._row_by_position(table, relegation_line_pos)
        if relegation_line and row.position >= total_teams - 5:
            safety_gap = row.points - relegation_line.points
            if safety_gap <= max(3, min(8, remaining * 2)):
                adj += 0.008

        # No-stakes late-season mid-table teams get a small negative adjustment.
        if late_season and 8 <= row.position <= max(8, total_teams - 6):
            top_gap = row.points - (cutoff.points if cutoff else row.points)
            bottom_gap = row.points - (relegation_line.points if relegation_line else row.points)
            if abs(top_gap) > 8 and bottom_gap > 8:
                adj -= 0.006

        return clamp(adj, -0.025, 0.025)

    def relative_adjustment(self, home_team: str, away_team: str, standings: Optional[List[StandingRow]] = None, competition_type: str = "league") -> Dict[str, float]:
        home = self.from_standings(home_team, standings, competition_type)
        away = self.from_standings(away_team, standings, competition_type)
        delta = clamp(home - away, -0.025, 0.025)
        return {"HOME": delta, "AWAY": -delta, "DRAW": -abs(delta) * 0.25}

    def _find_team(self, team_name: str, table: List[StandingRow]) -> Optional[StandingRow]:
        target = self._norm(team_name)
        for row in table:
            if self._norm(row.team_name) == target:
                return row
        # fuzzy-lite contains check, useful for small naming differences.
        for row in table:
            rn = self._norm(row.team_name)
            if target in rn or rn in target:
                return row
        return None

    def _row_by_position(self, table: List[StandingRow], position: int) -> Optional[StandingRow]:
        for row in table:
            if row.position == position:
                return row
        return None

    def _norm(self, value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())
