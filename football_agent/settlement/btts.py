from __future__ import annotations

from football_agent.settlement.base import FixtureResult, SettlementInput, SettlementOutcome, is_abandoned_status, is_finished_status
from football_agent.settlement.profit import profit_for_status


def _both_scored(result: FixtureResult) -> bool:
    return int(result.home_score or 0) > 0 and int(result.away_score or 0) > 0


def settle_btts(pick: SettlementInput, result: FixtureResult) -> SettlementOutcome:
    status_code = result.status_code
    if not result.has_score:
        return SettlementOutcome.skipped("MISSING_SCORE", fixture_status=status_code)

    if is_abandoned_status(status_code):
        if not _both_scored(result):
            return SettlementOutcome.void("ABANDONED_BTTS_NOT_MATHEMATICALLY_DECIDED", fixture_status=status_code)
        actual = "BTTS_YES"
        outcome_status = "WIN" if pick.selection == actual else "LOSS"
        profit, stake_returned, win_fraction, loss_fraction = profit_for_status(outcome_status, pick.stake_units, pick.entry_odds)
        return SettlementOutcome(
            status=outcome_status,
            actual_outcome=actual,
            settlement_basis="ABANDONED_BTTS_MATHEMATICALLY_DECIDED",
            profit_units=profit,
            stake_returned_units=stake_returned,
            win_fraction=win_fraction,
            loss_fraction=loss_fraction,
        )

    if not is_finished_status(status_code):
        return SettlementOutcome.skipped("FIXTURE_NOT_FINISHED", fixture_status=status_code)

    actual = "BTTS_YES" if _both_scored(result) else "BTTS_NO"
    outcome_status = "WIN" if pick.selection == actual else "LOSS"
    profit, stake_returned, win_fraction, loss_fraction = profit_for_status(outcome_status, pick.stake_units, pick.entry_odds)
    return SettlementOutcome(
        status=outcome_status,
        actual_outcome=actual,
        settlement_basis="FINISHED_BTTS_FINAL_SCORE",
        profit_units=profit,
        stake_returned_units=stake_returned,
        win_fraction=win_fraction,
        loss_fraction=loss_fraction,
    )
