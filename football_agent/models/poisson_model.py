from __future__ import annotations

import math
from typing import Dict, Tuple
from football_agent.schemas import PoissonProjection
from football_agent.utils import clamp


class PoissonModel:
    """Poisson score model with optional Dixon-Coles low-score correction.

    The plain independent Poisson model treats home and away goals as independent.
    Real football scores show dependence around low-score outcomes, especially
    0-0, 1-0, 0-1 and 1-1. Dixon-Coles applies a compact correction around
    those cells and then renormalizes the full matrix.
    """

    def __init__(self, max_goals: int = 8, dixon_coles_rho: float = -0.08):
        self.max_goals = max_goals
        # Negative rho increases 0-0 and 1-1 while reducing one-goal split cells.
        self.dixon_coles_rho = clamp(dixon_coles_rho, -0.20, 0.20)

    def _poisson(self, lam: float, k: int) -> float:
        lam = clamp(lam, 0.05, 5.0)
        return math.exp(-lam) * lam**k / math.factorial(k)

    def _dixon_coles_tau(self, home_goals: int, away_goals: int, home_xg: float, away_xg: float, rho: float) -> float:
        """Dixon-Coles dependence adjustment for low scoring cells.

        Formula follows the classic low-score correction. Values are clamped to
        avoid invalid negative probabilities if a caller supplies an aggressive rho.
        """
        if home_goals == 0 and away_goals == 0:
            tau = 1 - (home_xg * away_xg * rho)
        elif home_goals == 0 and away_goals == 1:
            tau = 1 + (home_xg * rho)
        elif home_goals == 1 and away_goals == 0:
            tau = 1 + (away_xg * rho)
        elif home_goals == 1 and away_goals == 1:
            tau = 1 - rho
        else:
            tau = 1.0
        return clamp(tau, 0.25, 2.25)

    def project(self, home_xg: float, away_xg: float, use_dixon_coles: bool = True, rho: float | None = None) -> PoissonProjection:
        home_xg = clamp(home_xg, 0.05, 5.0)
        away_xg = clamp(away_xg, 0.05, 5.0)
        rho_value = self.dixon_coles_rho if rho is None else clamp(rho, -0.20, 0.20)
        matrix: Dict[Tuple[int, int], float] = {}
        for h in range(self.max_goals + 1):
            for a in range(self.max_goals + 1):
                p = self._poisson(home_xg, h) * self._poisson(away_xg, a)
                if use_dixon_coles:
                    p *= self._dixon_coles_tau(h, a, home_xg, away_xg, rho_value)
                matrix[(h, a)] = p
        total = sum(matrix.values())
        matrix = {k: v / total for k, v in matrix.items()}
        home = sum(v for (h, a), v in matrix.items() if h > a)
        draw = sum(v for (h, a), v in matrix.items() if h == a)
        away = sum(v for (h, a), v in matrix.items() if h < a)
        best_score, best_p = max(matrix.items(), key=lambda kv: kv[1])
        over_25 = sum(v for (h, a), v in matrix.items() if h + a > 2.5)
        btts_yes = sum(v for (h, a), v in matrix.items() if h > 0 and a > 0)
        return PoissonProjection(
            home_xg=home_xg,
            away_xg=away_xg,
            most_likely_score=f"{best_score[0]}-{best_score[1]}",
            score_probability=best_p,
            outcome_probabilities={"HOME": home, "DRAW": draw, "AWAY": away},
            over_under={"OVER_2_5": over_25, "UNDER_2_5": 1 - over_25},
            btts={"YES": btts_yes, "NO": 1 - btts_yes},
        )

    def home_adjustment_pp(self, projection: PoissonProjection) -> float:
        return clamp((projection.outcome_probabilities["HOME"] - projection.outcome_probabilities["AWAY"]) * 0.05, -0.04, 0.04)
