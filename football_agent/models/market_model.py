from __future__ import annotations

from typing import Dict
from football_agent.utils import clamp


class MarketModel:
    """Converts bookmaker odds into clean no-vig probabilities.

    Default uses proportional no-vig margin cleansing. Shin-style cleansing is exposed
    as an optional conservative approximation; proportional is the production default
    because it is robust with sparse bookmaker data.
    """

    REQUIRED = {"HOME", "DRAW", "AWAY"}

    def raw_implied_probabilities(self, odds: Dict[str, float]) -> Dict[str, float]:
        self._validate_odds(odds)
        return {k: 1.0 / float(v) for k, v in odds.items() if k in self.REQUIRED}

    def overround(self, odds: Dict[str, float]) -> float:
        return sum(self.raw_implied_probabilities(odds).values())

    def no_vig_probabilities(self, odds: Dict[str, float]) -> Dict[str, float]:
        raw = self.raw_implied_probabilities(odds)
        total = sum(raw.values())
        if total <= 0:
            raise ValueError("Overround is ongeldig.")
        return {k: v / total for k, v in raw.items()}

    def fair_odds(self, odds: Dict[str, float]) -> Dict[str, float]:
        probs = self.no_vig_probabilities(odds)
        return {k: (1.0 / v if v > 0 else 999.0) for k, v in probs.items()}

    def shin_probabilities(self, odds: Dict[str, float]) -> Dict[str, float]:
        # Conservative Shin-like approximation. It removes more margin from shorter odds.
        # For robust operations with sparse odds, no_vig_probabilities remains preferred.
        raw = self.raw_implied_probabilities(odds)
        over = sum(raw.values())
        margin = max(0.0, over - 1.0)
        if margin <= 0:
            return self.no_vig_probabilities(odds)
        adjusted = {}
        for k, p in raw.items():
            penalty = margin * (p / over) ** 1.35
            adjusted[k] = max(0.0001, p - penalty)
        total = sum(adjusted.values())
        return {k: v / total for k, v in adjusted.items()}

    def edge(self, model_probability: float, market_probability: float) -> float:
        return model_probability - market_probability

    def _validate_odds(self, odds: Dict[str, float]) -> None:
        missing = self.REQUIRED.difference(odds.keys())
        if missing:
            raise ValueError(f"Ontbrekende 1X2 odds: {sorted(missing)}")
        for key in self.REQUIRED:
            if float(odds[key]) <= 1.0:
                raise ValueError(f"Odd voor {key} moet groter zijn dan 1.0")
