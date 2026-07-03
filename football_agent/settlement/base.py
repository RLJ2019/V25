from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_decimal(value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class FixtureResult:
    fixture_id: str
    status_short: str
    status_long: str = ""
    kickoff_utc: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    elapsed: Optional[int] = None
    source: str = "api-football"

    @property
    def status_code(self) -> str:
        return normalize_status(self.status_short or self.status_long)

    @property
    def has_score(self) -> bool:
        return self.home_score is not None and self.away_score is not None

    @property
    def total_goals(self) -> Optional[int]:
        if not self.has_score:
            return None
        return int(self.home_score or 0) + int(self.away_score or 0)


@dataclass(frozen=True)
class SettlementInput:
    pick_id: str
    fixture_id: str
    market: str
    selection: str
    stake_units: Decimal
    entry_odds: Decimal
    model_probability: Optional[Decimal] = None
    market_probability: Optional[Decimal] = None
    line: Optional[Decimal] = None
    bookmaker: Optional[str] = None
    kickoff_utc: Optional[str] = None


@dataclass
class SettlementOutcome:
    status: str
    actual_outcome: str
    settlement_basis: str
    profit_units: Decimal = Decimal("0")
    stake_returned_units: Decimal = Decimal("0")
    win_fraction: Decimal = Decimal("0")
    loss_fraction: Decimal = Decimal("0")
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_writeable(self) -> bool:
        return self.status not in {"SKIPPED", "OPEN"}

    @classmethod
    def skipped(cls, basis: str, **details: Any) -> "SettlementOutcome":
        return cls(status="SKIPPED", actual_outcome="SKIPPED", settlement_basis=basis, details=dict(details))

    @classmethod
    def void(cls, basis: str, **details: Any) -> "SettlementOutcome":
        return cls(status="VOID", actual_outcome="VOID", settlement_basis=basis, details=dict(details))


FINISHED_STATUSES = {
    "FT",
    "AET",
    "PEN",
    "MATCH FINISHED",
    "AFTER EXTRA TIME",
    "PENALTY SHOOTOUT",
    "FINISHED",
}
POSTPONED_STATUSES = {"PST", "POSTPONED"}
CANCELLED_STATUSES = {"CANC", "CANCELLED", "CANCELED"}
ABANDONED_STATUSES = {"ABD", "ABANDONED"}
LIVE_OR_OPEN_STATUSES = {
    "NS",
    "TBD",
    "1H",
    "HT",
    "2H",
    "ET",
    "BT",
    "P",
    "SUSP",
    "INT",
    "LIVE",
    "IN PLAY",
    "NOT STARTED",
    "TIME TO BE DEFINED",
}


def normalize_status(status: str | None) -> str:
    return str(status or "").strip().upper()


def is_finished_status(status: str | None) -> bool:
    return normalize_status(status) in FINISHED_STATUSES


def is_postponed_status(status: str | None) -> bool:
    return normalize_status(status) in POSTPONED_STATUSES


def is_cancelled_status(status: str | None) -> bool:
    return normalize_status(status) in CANCELLED_STATUSES


def is_abandoned_status(status: str | None) -> bool:
    return normalize_status(status) in ABANDONED_STATUSES


def is_open_or_live_status(status: str | None) -> bool:
    return normalize_status(status) in LIVE_OR_OPEN_STATUSES
