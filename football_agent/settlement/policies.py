from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import os
from typing import Optional

from football_agent.settlement.base import FixtureResult, SettlementOutcome, is_postponed_status, is_cancelled_status, is_open_or_live_status


SETTLEMENT_POLICY_VERSION = "v25.1.3-default-conservative"


def postponed_void_after_hours() -> int:
    try:
        return max(1, int(os.getenv("POSTPONED_VOID_AFTER_HOURS", "36")))
    except (TypeError, ValueError):
        return 36


def parse_dt(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def status_precheck(result: FixtureResult, now_utc: Optional[datetime] = None) -> Optional[SettlementOutcome]:
    status = result.status_code
    now = now_utc or datetime.now(timezone.utc)
    kickoff = parse_dt(result.kickoff_utc)

    if is_open_or_live_status(status):
        return SettlementOutcome.skipped("FIXTURE_NOT_FINISHED", fixture_status=status)

    if is_postponed_status(status):
        if kickoff is None:
            return SettlementOutcome.skipped("POSTPONED_MISSING_KICKOFF", fixture_status=status)
        age_hours = (now - kickoff).total_seconds() / 3600.0
        if age_hours < postponed_void_after_hours():
            return SettlementOutcome.skipped("POSTPONED_WITHIN_GRACE_PERIOD", fixture_status=status, age_hours=round(age_hours, 3))
        return SettlementOutcome.void("POSTPONED_GRACE_EXPIRED", fixture_status=status, age_hours=round(age_hours, 3))

    if is_cancelled_status(status):
        return SettlementOutcome.void("CANCELLED_FIXTURE", fixture_status=status)

    return None
