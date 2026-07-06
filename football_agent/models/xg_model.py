from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from football_agent.utils import clamp


def _parse_utc(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


@dataclass
class TeamMatchPerformance:
    match_date_utc: str
    xg_for: Optional[float] = None
    xg_against: Optional[float] = None
    goals_for: Optional[float] = None
    goals_against: Optional[float] = None
    is_home: Optional[bool] = None
    # V25.0.5: normalize all match production to per-90. Modern matches can run
    # 97-102 minutes; raw per-match xG can overstate repeatable team strength.
    minutes_played: Optional[float] = 90.0
    # V25.0.6: game-state normalized inputs reduce garbage-time distortion.
    # These values should contain xG only when the match is tied or within one goal,
    # if the data provider can supply that split. The model falls back to raw xG.
    game_state_xg_for: Optional[float] = None
    game_state_xg_against: Optional[float] = None
    game_state_minutes: Optional[float] = None


@dataclass
class TeamFormStats:
    # Legacy aggregate inputs are treated as per-90/per-match estimates when detailed
    # minutes are unavailable. Prefer recent_matches with minutes_played for production.
    xg_for_last5: Optional[float] = None
    xg_against_last5: Optional[float] = None
    goals_for_last5: Optional[float] = None
    goals_against_last5: Optional[float] = None
    home_xg_for: Optional[float] = None
    away_xg_for: Optional[float] = None
    recent_matches: List[TeamMatchPerformance] = field(default_factory=list)


class XGModel:
    """Rolling xG90 model with optional exponential time decay.

    V25.0.5 normalizes match-level xG/goals to per-90 before applying time decay.
    That reduces data drift caused by longer stoppage time and makes historical
    xG more comparable with current xG.
    """

    def __init__(self, half_life_days: float = 21.0, prefer_game_state_xg: bool = True):
        self.half_life_days = max(1.0, half_life_days)
        self.decay_lambda = math.log(2) / self.half_life_days
        self.prefer_game_state_xg = prefer_game_state_xg

    def _per90(self, value: Optional[float], minutes: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        mins = 90.0 if minutes is None else max(1.0, float(minutes))
        return float(value) * 90.0 / mins

    def _value_for_attr(self, match: TeamMatchPerformance, attr: str) -> tuple[Optional[float], Optional[float]]:
        if self.prefer_game_state_xg and attr == "xg_for" and match.game_state_xg_for is not None:
            return match.game_state_xg_for, match.game_state_minutes or match.minutes_played
        if self.prefer_game_state_xg and attr == "xg_against" and match.game_state_xg_against is not None:
            return match.game_state_xg_against, match.game_state_minutes or match.minutes_played
        return getattr(match, attr, None), match.minutes_played

    def _weighted_recent_average(self, matches: List[TeamMatchPerformance], attr: str, as_of_utc: Optional[str] = None) -> Optional[float]:
        if not matches:
            return None
        as_of = _parse_utc(as_of_utc or "") or datetime.now(timezone.utc)
        weighted_sum = 0.0
        weight_total = 0.0
        for m in matches:
            raw_value, minutes = self._value_for_attr(m, attr)
            value = self._per90(raw_value, minutes)
            dt = _parse_utc(m.match_date_utc)
            if value is None or dt is None:
                continue
            age_days = max(0.0, (as_of - dt).total_seconds() / 86400.0)
            weight = math.exp(-self.decay_lambda * age_days)
            weighted_sum += float(value) * weight
            weight_total += weight
        if weight_total <= 0:
            return None
        return weighted_sum / weight_total

    def estimate_team_xg(self, attack: TeamFormStats, opponent: TeamFormStats, fallback: float = 1.25, as_of_utc: Optional[str] = None) -> float:
        pieces = []
        recent_attack_xg90 = self._weighted_recent_average(attack.recent_matches, "xg_for", as_of_utc)
        recent_opp_xga90 = self._weighted_recent_average(opponent.recent_matches, "xg_against", as_of_utc)
        recent_goals90 = self._weighted_recent_average(attack.recent_matches, "goals_for", as_of_utc)

        if recent_attack_xg90 is not None:
            pieces.append(recent_attack_xg90)
        elif attack.xg_for_last5 is not None:
            pieces.append(attack.xg_for_last5)

        if recent_opp_xga90 is not None:
            pieces.append(recent_opp_xga90)
        elif opponent.xg_against_last5 is not None:
            pieces.append(opponent.xg_against_last5)

        if recent_goals90 is not None:
            pieces.append(0.65 * recent_goals90 + 0.35 * fallback)
        elif attack.goals_for_last5 is not None:
            pieces.append(0.65 * attack.goals_for_last5 + 0.35 * fallback)

        if not pieces:
            return fallback
        return clamp(sum(pieces) / len(pieces), 0.25, 3.25)

    def adjustment_pp(self, home_xg: float, away_xg: float) -> float:
        return clamp((home_xg - away_xg) * 0.035, -0.08, 0.08)
