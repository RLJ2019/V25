from __future__ import annotations

from decimal import Decimal

from football_agent.settlement.base import FixtureResult, SettlementInput, SettlementOutcome, is_abandoned_status, is_finished_status
from football_agent.settlement.market_mapping import is_supported_total_line
from football_agent.settlement.profit import profit_for_status


def settle_totals(pick: SettlementInput, result: FixtureResult) -> SettlementOutcome:
    status_code = result.status_code
    line = pick.line
    if line is None:
        return SettlementOutcome.skipped("SKIPPED_MISSING_TOTAL_LINE", fixture_status=status_code)
    if not is_supported_total_line(line):
        return SettlementOutcome.skipped("SKIPPED_UNSUPPORTED_LINE", fixture_status=status_code, line=str(line))
    if not result.has_score:
        return SettlementOutcome.skipped("MISSING_SCORE", fixture_status=status_code)

    total = Decimal(int(result.total_goals or 0))
    selection = str(pick.selection or "").upper()

    if is_abandoned_status(status_code):
        # Conservative mathematical-certainty policy: an over is decided as soon as
        # goals exceed the line. Under is then necessarily lost. Otherwise all
        # totals remain void because additional goals could still occur.
        if total > line:
            actual = f"OVER_{str(line).replace('.', '_')}"
            outcome_status = "WIN" if selection == "OVER" else "LOSS"
            profit, stake_returned, win_fraction, loss_fraction = profit_for_status(outcome_status, pick.stake_units, pick.entry_odds)
            return SettlementOutcome(
                status=outcome_status,
                actual_outcome=actual,
                settlement_basis="ABANDONED_TOTALS_MATHEMATICALLY_DECIDED",
                profit_units=profit,
                stake_returned_units=stake_returned,
                win_fraction=win_fraction,
                loss_fraction=loss_fraction,
                details={"total_goals": int(total), "line": str(line)},
            )
        return SettlementOutcome.void("ABANDONED_TOTALS_NOT_MATHEMATICALLY_DECIDED", fixture_status=status_code, total_goals=int(total), line=str(line))

    if not is_finished_status(status_code):
        return SettlementOutcome.skipped("FIXTURE_NOT_FINISHED", fixture_status=status_code)

    if total > line:
        actual = f"OVER_{str(line).replace('.', '_')}"
    elif total < line:
        actual = f"UNDER_{str(line).replace('.', '_')}"
    else:
        actual = f"PUSH_{str(line).replace('.', '_')}"

    if actual.startswith("PUSH"):
        outcome_status = "PUSH"
    elif selection == "OVER" and actual.startswith("OVER"):
        outcome_status = "WIN"
    elif selection == "UNDER" and actual.startswith("UNDER"):
        outcome_status = "WIN"
    else:
        outcome_status = "LOSS"

    profit, stake_returned, win_fraction, loss_fraction = profit_for_status(outcome_status, pick.stake_units, pick.entry_odds)
    return SettlementOutcome(
        status=outcome_status,
        actual_outcome=actual,
        settlement_basis="FINISHED_TOTALS_FINAL_SCORE",
        profit_units=profit,
        stake_returned_units=stake_returned,
        win_fraction=win_fraction,
        loss_fraction=loss_fraction,
        details={"total_goals": int(total), "line": str(line)},
    )
