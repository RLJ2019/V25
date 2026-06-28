from __future__ import annotations

from football_agent.utils import clamp


class RefereeModel:
    def chaos_adjustment(self, avg_cards: float | None = None, avg_penalties: float | None = None, team_aggression_delta: float = 0.0) -> float:
        if avg_cards is None and avg_penalties is None:
            return 0.0
        cards = avg_cards or 4.0
        pens = avg_penalties or 0.25
        chaos = (cards - 4.0) * 0.002 + (pens - 0.25) * 0.010 + team_aggression_delta * 0.003
        return clamp(chaos, -0.015, 0.015)
