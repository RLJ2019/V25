from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

from football_agent.schemas import OddsSnapshot


def parse_utc(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


@dataclass
class OddsFreshness:
    fresh: bool
    newest_timestamp_utc: str
    age_minutes: Optional[float]
    reason: str


class OddsTimelineAnalyzer:
    def __init__(self, max_age_minutes: int = 180):
        self.max_age_minutes = max_age_minutes

    def freshness(self, odds: Iterable[OddsSnapshot], now: Optional[datetime] = None) -> OddsFreshness:
        now = now or datetime.now(timezone.utc)
        parsed = [(o, parse_utc(o.timestamp_utc)) for o in odds or []]
        parsed = [(o, ts) for o, ts in parsed if ts is not None]
        if not parsed:
            return OddsFreshness(False, "", None, "Geen geldige odds-timestamp beschikbaar.")
        newest_o, newest_ts = max(parsed, key=lambda pair: pair[1])
        age = max(0.0, (now - newest_ts).total_seconds() / 60.0)
        fresh = age <= self.max_age_minutes
        return OddsFreshness(
            fresh=fresh,
            newest_timestamp_utc=newest_o.timestamp_utc,
            age_minutes=age,
            reason=(f"Odds zijn {age:.0f} minuten oud." if fresh else f"Odds zijn te oud: {age:.0f} minuten."),
        )

    def has_closing_reference(self, odds: Iterable[OddsSnapshot]) -> bool:
        return any(o.closing_odds and o.closing_odds > 1.0 for o in odds or [])

    def sharp_implied_movement(self, odds: Iterable[OddsSnapshot]) -> Dict[str, float]:
        """Signed sharp-market movement per selection.

        Positive = sharp implied probability increased since opening (market supports selection).
        Negative = sharp implied probability decreased (market drifts against selection).
        Uses raw implied probability because this is a directional signal, not a final baseline.
        """
        best: Dict[str, OddsSnapshot] = {}
        for o in odds or []:
            if o.profile != "sharp" or not o.opening_odds or o.opening_odds <= 1 or o.odds <= 1:
                continue
            cur = best.get(o.selection)
            if cur is None or parse_utc(o.timestamp_utc or "") or True:
                best[o.selection] = o
        movement: Dict[str, float] = {}
        for sel, o in best.items():
            opening_prob = 1.0 / float(o.opening_odds)
            current_prob = 1.0 / float(o.odds)
            movement[sel] = current_prob - opening_prob
        return movement
