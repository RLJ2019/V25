from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from football_agent.settlement.base import FixtureResult, SettlementInput, SettlementOutcome, to_decimal, utc_now_iso
from football_agent.settlement.btts import settle_btts
from football_agent.settlement.clv import calculate_clv
from football_agent.settlement.market_mapping import MarketMappingError, normalize_pick_market_selection_line
from football_agent.settlement.one_x_two import settle_1x2
from football_agent.settlement.policies import SETTLEMENT_POLICY_VERSION, status_precheck
from football_agent.settlement.totals import settle_totals


VALUE_PICK_STATUSES = {"VALUE_PICK", "VALUE", "ALERT"}
SKIP_PICK_STATUSES = {"NO_BET", "WATCHLIST", "SKIPPED"}


class SettlementService:
    def __init__(self, repository: Any, result_provider: Any, *, dry_run: bool = True, now_utc: Optional[datetime] = None):
        self.repository = repository
        self.result_provider = result_provider
        self.dry_run = dry_run
        self.now_utc = now_utc or datetime.now(timezone.utc)

    def _input_from_pick(self, row: Mapping[str, Any], fixture_row: Optional[Mapping[str, Any]] = None) -> SettlementInput | SettlementOutcome:
        status = str(row.get("status") or "").upper()
        if status in SKIP_PICK_STATUSES or status not in VALUE_PICK_STATUSES:
            return SettlementOutcome.skipped("SKIPPED_NOT_VALUE_PICK", pick_status=status)
        stake = to_decimal(row.get("stake_units"), Decimal("0")) or Decimal("0")
        odds = to_decimal(row.get("entry_odds"))
        if stake <= 0:
            return SettlementOutcome.skipped("SKIPPED_ZERO_STAKE", stake_units=str(stake))
        if odds is None or odds <= 0:
            return SettlementOutcome.skipped("SKIPPED_MISSING_ENTRY_ODDS")
        fixture_id = str(row.get("fixture_id") or "")
        if not fixture_id:
            return SettlementOutcome.skipped("SKIPPED_MISSING_FIXTURE_ID")
        market = str(row.get("market") or "")
        selection = str(row.get("selection") or "")
        try:
            canonical_market, canonical_selection, line = normalize_pick_market_selection_line(market, selection, row.get("line"))
        except MarketMappingError as exc:
            return SettlementOutcome.skipped(exc.code, message=str(exc), market=market, selection=selection, line=row.get("line"))
        return SettlementInput(
            pick_id=str(row.get("pick_id") or ""),
            fixture_id=fixture_id,
            market=canonical_market,
            selection=canonical_selection,
            line=line,
            stake_units=stake,
            entry_odds=odds,
            model_probability=to_decimal(row.get("model_probability")),
            market_probability=to_decimal(row.get("market_probability")),
            bookmaker=row.get("bookmaker"),
            kickoff_utc=str(row.get("kickoff_utc") or (fixture_row or {}).get("kickoff_utc") or "") or None,
        )

    def _settle_market(self, pick: SettlementInput, result: FixtureResult) -> SettlementOutcome:
        precheck = status_precheck(result, self.now_utc)
        if precheck:
            return precheck
        if pick.market == "1X2":
            return settle_1x2(pick, result)
        if pick.market == "BTTS":
            return settle_btts(pick, result)
        if pick.market == "OVER_UNDER":
            return settle_totals(pick, result)
        return SettlementOutcome.skipped("SKIPPED_UNSUPPORTED_MARKET", market=pick.market)

    @staticmethod
    def _dec_to_float(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        return value

    def _build_row(self, pick_row: Mapping[str, Any], fixture_row: Mapping[str, Any] | None, pick: SettlementInput, result: FixtureResult, outcome: SettlementOutcome, clv: Any) -> Dict[str, Any]:
        details = dict(outcome.details or {})
        details.update({
            "dry_run": self.dry_run,
            "policy_version": SETTLEMENT_POLICY_VERSION,
            "fixture_status_short": result.status_short,
            "fixture_status_long": result.status_long,
        })
        row = {
            "pick_id": pick.pick_id,
            "fixture_id": pick.fixture_id,
            "kickoff_utc": pick.kickoff_utc or result.kickoff_utc or (fixture_row or {}).get("kickoff_utc"),
            "fixture_status": result.status_code,
            "final_score_home": result.home_score,
            "final_score_away": result.away_score,
            "score_source": result.source,
            "market": pick.market,
            "selection": pick.selection,
            "line": self._dec_to_float(pick.line),
            "stake_units": self._dec_to_float(pick.stake_units),
            "entry_odds": self._dec_to_float(pick.entry_odds),
            "model_probability": self._dec_to_float(pick.model_probability),
            "market_probability": self._dec_to_float(pick.market_probability),
            "actual_outcome": outcome.actual_outcome,
            "status": outcome.status,
            "profit_units": self._dec_to_float(outcome.profit_units),
            "stake_returned_units": self._dec_to_float(outcome.stake_returned_units),
            "win_fraction": self._dec_to_float(outcome.win_fraction),
            "loss_fraction": self._dec_to_float(outcome.loss_fraction),
            "closing_odds": self._dec_to_float(clv.closing_odds),
            "closing_bookmaker": clv.closing_bookmaker,
            "closing_snapshot_id": clv.closing_snapshot_id,
            "overround": self._dec_to_float(clv.overround),
            "clv_odds": self._dec_to_float(clv.clv_market_movement),
            "clv_probability": self._dec_to_float(clv.clv_model_vs_close),
            "clv_market_movement": self._dec_to_float(clv.clv_market_movement),
            "clv_model_vs_close": self._dec_to_float(clv.clv_model_vs_close),
            "clv_method": clv.clv_method,
            "clv_warning": clv.clv_warning,
            "settlement_basis": outcome.settlement_basis,
            "settlement_policy_version": SETTLEMENT_POLICY_VERSION,
            "settlement_details": details,
            "settled_at": utc_now_iso(),
            "updated_at_utc": utc_now_iso(),
        }
        return row

    def settle_once(self, limit: int = 1000) -> Dict[str, Any]:
        picks = self.repository.fetch_unsettled_value_picks(limit=limit)
        rows_to_write: List[Dict[str, Any]] = []
        settlements: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        for pick_row in picks:
            fixture_id = str(pick_row.get("fixture_id") or "")
            fixture_row = self.repository.fetch_fixture_by_id(fixture_id) if fixture_id else None
            normalized = self._input_from_pick(pick_row, fixture_row)
            if isinstance(normalized, SettlementOutcome):
                skipped.append({"pick_id": pick_row.get("pick_id"), "fixture_id": fixture_id, "basis": normalized.settlement_basis, "details": normalized.details})
                continue
            pick = normalized
            result = self.result_provider.get_fixture_result(pick.fixture_id, fixture_row=fixture_row)
            if result is None:
                skipped.append({"pick_id": pick.pick_id, "fixture_id": fixture_id, "basis": "MISSING_FIXTURE_RESULT"})
                continue
            outcome = self._settle_market(pick, result)
            if not outcome.is_writeable:
                skipped.append({"pick_id": pick.pick_id, "fixture_id": fixture_id, "basis": outcome.settlement_basis, "details": outcome.details})
                continue
            odds_rows = self.repository.fetch_closing_odds_bundle(pick.fixture_id, pick.market, pick.selection, line=pick.line)
            clv = calculate_clv(
                entry_odds=pick.entry_odds,
                model_probability=pick.model_probability,
                market=pick.market,
                selection=pick.selection,
                line=pick.line,
                closing_bookmaker=pick.bookmaker,
                quotes=odds_rows,
            )
            row = self._build_row(pick_row, fixture_row, pick, result, outcome, clv)
            settlements.append(row)
            rows_to_write.append(row)

        if rows_to_write and not self.dry_run:
            self.repository.upsert_settlements(rows_to_write)

        report = {
            "status": "OK",
            "dry_run": self.dry_run,
            "policy_version": SETTLEMENT_POLICY_VERSION,
            "candidate_picks": len(picks),
            "writeable_settlements": len(rows_to_write),
            "written_settlements": 0 if self.dry_run else len(rows_to_write),
            "skipped": len(skipped),
            "skipped_details": skipped,
            "settlements": settlements,
        }
        return report


def write_settlement_outputs(report: Mapping[str, Any], output_dir: str | Path = "output") -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "settlement_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    settlements = list(report.get("settlements", []) or [])
    if settlements:
        keys = sorted({key for row in settlements for key in row.keys()})
        with (out / "settlements.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            for row in settlements:
                writer.writerow({key: json.dumps(value, default=str) if isinstance(value, (dict, list)) else value for key, value in row.items()})
