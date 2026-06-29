from __future__ import annotations

from collections import Counter
from typing import Iterable, Dict
from football_agent.schemas import PickDecision


def summarize(picks: Iterable[PickDecision]) -> Dict:
    picks = list(picks)
    c = Counter(p.status for p in picks)
    return {"scanned": len(picks), "value_picks": c.get("VALUE_PICK", 0), "watchlist": c.get("WATCHLIST", 0), "no_bet": c.get("NO_BET", 0)}
