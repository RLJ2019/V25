from __future__ import annotations

from collections import defaultdict
from typing import Iterable, List

from football_agent.schemas import PickDecision


class ExposureManager:
    """Simple correlation/exposure guardrail.

    This prevents the Telegram output from concentrating all risk in one league,
    one team, or one fixture. It does not change model probabilities; it only
    downgrades lower-ranked value picks to Watchlist when portfolio exposure is
    too concentrated.
    """

    def __init__(self, max_value_picks_per_competition: int = 3, max_value_picks_per_team: int = 1, max_value_picks_per_fixture: int = 1, max_total_units_per_day: float = 3.0):
        self.max_value_picks_per_competition = max_value_picks_per_competition
        self.max_value_picks_per_team = max_value_picks_per_team
        self.max_value_picks_per_fixture = max_value_picks_per_fixture
        self.max_total_units_per_day = max(0.0, max_total_units_per_day)

    def apply(self, picks: Iterable[PickDecision]) -> List[PickDecision]:
        ordered = list(picks)
        value_picks = [p for p in ordered if p.status == "VALUE_PICK"]
        value_picks.sort(key=lambda p: (p.value_decision.expected_value if p.value_decision else 0.0), reverse=True)
        comp_counts = defaultdict(int)
        team_counts = defaultdict(int)
        fixture_counts = defaultdict(int)
        allowed_ids = set()
        used_units = 0.0
        for p in value_picks:
            f = p.fixture
            teams = [f.home_team.lower(), f.away_team.lower()]
            stake_units = max(0.0, float(getattr(p, "stake_units", 0.0) or 0.0))
            too_much = (
                comp_counts[f.competition_key] >= self.max_value_picks_per_competition
                or fixture_counts[f.id] >= self.max_value_picks_per_fixture
                or any(team_counts[t] >= self.max_value_picks_per_team for t in teams)
                or (used_units + stake_units > self.max_total_units_per_day)
            )
            if not too_much:
                allowed_ids.add(id(p))
                comp_counts[f.competition_key] += 1
                fixture_counts[f.id] += 1
                for t in teams:
                    team_counts[t] += 1
                used_units += stake_units
        for p in ordered:
            if p.status == "VALUE_PICK" and id(p) not in allowed_ids:
                p.status = "WATCHLIST"
                p.advice = "Monitoren: value gevonden, maar gedowngraded door exposure/correlatie-limiet."
                p.explanation_facts.setdefault("portfolio_guardrails", []).append("Downgrade door exposure management.")
                p.stake_units = 0.0
                p.fractional_kelly = 0.0
                if p.value_decision:
                    p.value_decision.stake_units = 0.0
                    p.value_decision.fractional_kelly = 0.0
        return ordered
