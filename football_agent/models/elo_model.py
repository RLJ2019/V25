from __future__ import annotations

import math
from typing import Dict, Tuple
from football_agent.utils import clamp


class EloModel:
    def __init__(
        self,
        default_elo: float = 1500.0,
        k_factor: float = 24.0,
        home_advantage: float = 55.0,
        promoted_elo: float = 1435.0,
    ):
        self.default_elo = default_elo
        self.k_factor = k_factor
        self.home_advantage = home_advantage
        self.promoted_elo = promoted_elo
        self.ratings: Dict[str, float] = {}

    def get(self, team: str, is_promoted: bool = False, promoted_elo: float | None = None) -> float:
        key = team.lower()
        if key in self.ratings:
            return self.ratings[key]
        if is_promoted:
            return float(promoted_elo if promoted_elo is not None else self.promoted_elo)
        return self.default_elo

    def set(self, team: str, rating: float) -> None:
        self.ratings[team.lower()] = float(rating)

    def expected_home(
        self,
        home_team: str,
        away_team: str,
        home_is_promoted: bool = False,
        away_is_promoted: bool = False,
        promoted_elo: float | None = None,
    ) -> float:
        home = self.get(home_team, is_promoted=home_is_promoted, promoted_elo=promoted_elo) + self.home_advantage
        away = self.get(away_team, is_promoted=away_is_promoted, promoted_elo=promoted_elo)
        return 1.0 / (1.0 + 10 ** ((away - home) / 400.0))

    def update(self, home_team: str, away_team: str, home_goals: int, away_goals: int) -> Tuple[float, float]:
        exp_home = self.expected_home(home_team, away_team)
        if home_goals > away_goals:
            actual_home = 1.0
        elif home_goals == away_goals:
            actual_home = 0.5
        else:
            actual_home = 0.0
        margin = abs(home_goals - away_goals)
        mov_multiplier = math.log(margin + 1.0) + 1.0
        delta = self.k_factor * mov_multiplier * (actual_home - exp_home)
        new_home = self.get(home_team) + delta
        new_away = self.get(away_team) - delta
        self.set(home_team, new_home)
        self.set(away_team, new_away)
        return new_home, new_away

    def adjustment_pp(
        self,
        home_team: str,
        away_team: str,
        home_is_promoted: bool = False,
        away_is_promoted: bool = False,
        promoted_elo: float | None = None,
    ) -> float:
        # Convert Elo expectation into a bounded percentage-point overlay around market-neutral 50%.
        # V25.0.6: promoted teams receive a Bayesian lower prior until live match data
        # overwrites the rating, avoiding early-season promoted-team overestimation.
        exp = self.expected_home(
            home_team,
            away_team,
            home_is_promoted=home_is_promoted,
            away_is_promoted=away_is_promoted,
            promoted_elo=promoted_elo,
        )
        return clamp((exp - 0.50) * 0.18, -0.08, 0.08)
