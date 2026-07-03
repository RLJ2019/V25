from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


Q = Decimal("0.000001")


def q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Q, rounding=ROUND_HALF_UP)


def profit_for_status(status: str, stake_units: Decimal, entry_odds: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Return profit, stake_returned, win_fraction, loss_fraction.

    V25.1.3 supports WIN/LOSS/PUSH/VOID and keeps HALF_* statuses ready for
    future split-line settlement without enabling quarter lines yet.
    """
    status = str(status or "").upper()
    stake = Decimal(stake_units or 0)
    odds = Decimal(entry_odds or 0)
    if status == "WIN":
        return q(stake * (odds - Decimal("1"))), q(stake), Decimal("1"), Decimal("0")
    if status == "LOSS":
        return q(-stake), Decimal("0"), Decimal("0"), Decimal("1")
    if status in {"PUSH", "VOID"}:
        return Decimal("0"), q(stake), Decimal("0"), Decimal("0")
    if status == "HALF_WIN":
        return q(stake * Decimal("0.5") * (odds - Decimal("1"))), q(stake), Decimal("0.5"), Decimal("0")
    if status == "HALF_LOSS":
        return q(-stake * Decimal("0.5")), q(stake * Decimal("0.5")), Decimal("0"), Decimal("0.5")
    return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")
