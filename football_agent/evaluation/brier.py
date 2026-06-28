from __future__ import annotations

from typing import Dict


def brier_score(probabilities: Dict[str, float], actual: str) -> float:
    return sum((probabilities.get(k, 0.0) - (1.0 if k == actual else 0.0)) ** 2 for k in ["HOME", "DRAW", "AWAY"])
