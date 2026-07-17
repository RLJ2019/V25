from __future__ import annotations

from decimal import Decimal

from football_agent.settlement.base import FixtureResult, SettlementInput, SettlementOutcome, is_abandoned_status, is_finished_status
from football_agent.settlement.profit import profit_for_status


def settle_1x2(pick: SettlementInput, result: FixtureResult) -> SettlementOutcome:
    status_code = result.status_code
    if is_abandoned_status(status_code):
        return SettlementOutcome.void("ABANDONED_1X2_CONSERVATIVE_VOID", fixture_status=status_code)
    if not is_finished_status(status_code):
        return SettlementOutcome.skipped("FIXTURE_NOT_FINISHED", fixture_status=status_code)
    if not result.has_score:
        return SettlementOutcome.skipped("MISSING_FINAL_SCORE", fixture_status=status_code)

    if int(result.home_score or 0) > int(result.away_score or 0):
        actual = "HOME"
    elif int(result.home_score or 0) < int(result.away_score or 0):
        actual = "AWAY"
    else:
        actual = "DRAW"

    outcome_status = "WIN" if pick.selection == actual else "LOSS"
    profit, stake_returned, win_fraction, loss_fraction = profit_for_status(outcome_status, pick.stake_units, pick.entry_odds)
    return SettlementOutcome(
        status=outcome_status,
        actual_outcome=actual,
        settlement_basis="FINISHED_1X2_FINAL_SCORE",
        profit_units=profit,
        stake_returned_units=stake_returned,
        win_fraction=win_fraction,
        loss_fraction=loss_fraction,
    )
