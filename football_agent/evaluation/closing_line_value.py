from __future__ import annotations


def clv_decimal(pick_odds: float, closing_odds: float) -> float:
    if closing_odds <= 1 or pick_odds <= 1:
        return 0.0
    return (pick_odds / closing_odds) - 1.0
