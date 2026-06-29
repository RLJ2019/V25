from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Iterable, List, Optional, Tuple


def _parse_date(value: str) -> datetime:
    # Accept YYYY-MM-DD or full ISO datetime.
    if "T" in value:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return datetime.fromisoformat(value + "T00:00:00+00:00").astimezone(timezone.utc)


def _parse_utc(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


@dataclass(frozen=True)
class BreakWindow:
    start_utc: datetime
    end_utc: datetime


class InternationalBreakFilter:
    """Detect first club fixtures after an international break.

    Default windows can be supplied through INTERNATIONAL_BREAK_WINDOWS:
        YYYY-MM-DD:YYYY-MM-DD,YYYY-MM-DD:YYYY-MM-DD

    We intentionally keep the windows configurable rather than hardcoding future
    FIFA dates that may move. If no windows are configured, the filter is inert.
    """

    def __init__(self, windows: Optional[Iterable[Tuple[str, str]]] = None, days_after: int = 7):
        self.days_after = max(1, int(days_after))
        if windows is None:
            windows = self._windows_from_env()
        self.windows: List[BreakWindow] = [BreakWindow(_parse_date(s), _parse_date(e)) for s, e in windows]

    def _windows_from_env(self) -> List[Tuple[str, str]]:
        raw = os.getenv("INTERNATIONAL_BREAK_WINDOWS", "").strip()
        if not raw:
            return []
        windows: List[Tuple[str, str]] = []
        for part in raw.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            start, end = part.split(":", 1)
            windows.append((start.strip(), end.strip()))
        return windows

    def is_post_break_fixture(self, kickoff_utc: str) -> bool:
        kickoff = _parse_utc(kickoff_utc)
        if not kickoff:
            return False
        for window in self.windows:
            if window.end_utc <= kickoff <= window.end_utc + timedelta(days=self.days_after):
                return True
        return False
