from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional
from football_agent.utils import clamp


@dataclass
class PlayerAbsence:
    player_name: str
    team: str
    position: str
    role: str = "rotation"  # key, starter, rotation
    side: Optional[str] = None  # left, right, central
    replacement_quality: float = 0.75  # fallback: 0 poor, 1 equal replacement
    # Optional dynamic quality inputs. If supplied, they override the static
    # replacement_quality with a capped ratio. This prevents Man City-style deep
    # squads and thin-squad teams from being treated the same.
    player_market_value: Optional[float] = None
    replacement_market_value: Optional[float] = None
    player_minutes_12m: Optional[float] = None
    replacement_minutes_12m: Optional[float] = None


class InjuryModel:
    BASE_IMPACT = {
        "GK": 0.045,
        "CB": 0.035,
        "LB": 0.025,
        "RB": 0.025,
        "DM": 0.025,
        "CM": 0.022,
        "AM": 0.028,
        "LW": 0.030,
        "RW": 0.030,
        "ST": 0.040,
    }
    ROLE_MULT = {"key": 1.45, "starter": 1.0, "rotation": 0.45}

    def __init__(self, max_total_impact: float = 0.12, max_line_impact: float = 0.08):
        self.max_total_impact = max_total_impact
        self.max_line_impact = max_line_impact

    def team_impact(self, absences: Iterable[PlayerAbsence]) -> float:
        absences = list(absences)
        linear = 0.0
        side_counts: Dict[str, int] = {}
        line_impact: Dict[str, float] = {"defense": 0.0, "midfield": 0.0, "attack": 0.0}
        for a in absences:
            base = self.BASE_IMPACT.get(a.position.upper(), 0.018)
            role_mult = self.ROLE_MULT.get(a.role, 0.65)
            replacement_quality = self._dynamic_replacement_quality(a)
            replacement_factor = clamp(1.0 - replacement_quality, 0.0, 1.0)
            impact = base * role_mult * (0.5 + replacement_factor)
            linear += impact
            line = self._line(a.position)
            line_impact[line] += impact
            if a.side:
                side_counts[a.side] = side_counts.get(a.side, 0) + 1

        synergy = 0.0
        for side, count in side_counts.items():
            if count >= 2:
                synergy += min(0.025, 0.008 * (count - 1))
        capped_lines = sum(clamp(v, 0.0, self.max_line_impact) for v in line_impact.values())
        total = min(linear + synergy, capped_lines + synergy, self.max_total_impact)
        return clamp(total, 0.0, self.max_total_impact)

    def _dynamic_replacement_quality(self, absence: PlayerAbsence) -> float:
        candidates = []
        if absence.player_market_value and absence.player_market_value > 0 and absence.replacement_market_value is not None:
            candidates.append(absence.replacement_market_value / absence.player_market_value)
        if absence.player_minutes_12m and absence.player_minutes_12m > 0 and absence.replacement_minutes_12m is not None:
            candidates.append(absence.replacement_minutes_12m / absence.player_minutes_12m)
        if not candidates:
            return clamp(absence.replacement_quality, 0.15, 1.05)
        # Blend market value and recent minutes if both exist. Cap above 1.0 to
        # allow strong squads to absorb an absence, but prevent negative impact.
        return clamp(sum(candidates) / len(candidates), 0.15, 1.05)

    def _line(self, position: str) -> str:
        p = position.upper()
        if p in {"GK", "CB", "LB", "RB"}:
            return "defense"
        if p in {"DM", "CM", "AM"}:
            return "midfield"
        return "attack"
