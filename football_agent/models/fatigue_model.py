from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from football_agent.utils import clamp, parse_iso_datetime


class FatigueModel:
    def __init__(self, max_penalty: float = 0.08):
        self.max_penalty = max_penalty

    def penalty(self, kickoff_utc: str, previous_match_utc: Optional[str] = None, european_midweek: bool = False, travel_km: float = 0.0, away_after_europe: bool = False) -> float:
        p = 0.0
        if previous_match_utc:
            ko = parse_iso_datetime(kickoff_utc)
            prev = parse_iso_datetime(previous_match_utc)
            if ko and prev:
                hours = (ko - prev).total_seconds() / 3600
                if hours < 72:
                    p += 0.025
                if hours < 96:
                    p += 0.012
        if european_midweek:
            p += 0.025
        if away_after_europe:
            p += 0.015
        if travel_km >= 1200:
            p += 0.020
        elif travel_km >= 600:
            p += 0.010
        return clamp(p, 0.0, self.max_penalty)
