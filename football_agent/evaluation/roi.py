from __future__ import annotations

from typing import Iterable, Dict


def settle_pick(selection: str, actual: str, odds: float, stake: float = 1.0) -> float:
    return (odds - 1.0) * stake if selection == actual else -stake


def roi(returns: Iterable[float], stakes: Iterable[float]) -> float:
    returns = list(returns)
    stakes = list(stakes)
    total_stake = sum(stakes)
    if total_stake == 0:
        return 0.0
    return sum(returns) / total_stake
