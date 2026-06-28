from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def parse_utc_datetime(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def hours_until(kickoff_utc: str, now: Optional[datetime] = None) -> Optional[float]:
    dt = parse_utc_datetime(kickoff_utc)
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (dt - now).total_seconds() / 3600.0


def time_window_for_fixture(kickoff_utc: str, now: Optional[datetime] = None) -> str:
    hrs = hours_until(kickoff_utc, now)
    if hrs is None:
        return "UNKNOWN"
    if hrs < 0:
        return "LIVE_OR_CLOSED"
    if hrs <= 1.25:
        return "FINAL"
    if hrs <= 6:
        return "PREMATCH"
    if hrs <= 72:
        return "EARLY"
    return "FUTURE"


def minutes_until(kickoff_utc: str, now: Optional[datetime] = None) -> Optional[float]:
    hrs = hours_until(kickoff_utc, now)
    if hrs is None:
        return None
    return hrs * 60.0
