from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional, Tuple

from football_agent.settlement.base import to_decimal


PROVIDER_MARKET_ALIASES = {
    "1X2": {"1X2", "MATCH WINNER", "FULL TIME RESULT", "FULLTIME RESULT", "MATCH RESULT"},
    "BTTS": {"BTTS", "BOTH TEAMS TO SCORE", "BOTH TEAMS SCORE"},
    "OVER_UNDER": {"OVER_UNDER", "GOALS OVER/UNDER", "TOTAL GOALS", "OVER/UNDER", "TOTALS"},
}


class MarketMappingError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize_market(market: str | None) -> str:
    raw = str(market or "").strip().upper().replace("-", "_").replace(" ", "_")
    label = str(market or "").strip().upper()
    if raw in {"1X2", "MATCH_WINNER", "FULL_TIME_RESULT", "FULLTIME_RESULT", "MATCH_RESULT"} or label in PROVIDER_MARKET_ALIASES["1X2"]:
        return "1X2"
    if raw == "BTTS" or label in PROVIDER_MARKET_ALIASES["BTTS"] or "BOTH_TEAMS" in raw:
        return "BTTS"
    if raw.startswith("OVER_UNDER") or "OVER_UNDER" in raw or label in PROVIDER_MARKET_ALIASES["OVER_UNDER"] or "OVER/UNDER" in label:
        return "OVER_UNDER"
    raise MarketMappingError("SKIPPED_UNSUPPORTED_MARKET", f"Unsupported market: {market}")


def normalize_selection(market: str, selection: str | None) -> str:
    canonical_market = normalize_market(market)
    raw = str(selection or "").strip().upper().replace("-", "_").replace(" ", "_")
    if canonical_market == "1X2":
        if raw in {"HOME", "1"}:
            return "HOME"
        if raw in {"DRAW", "X"}:
            return "DRAW"
        if raw in {"AWAY", "2"}:
            return "AWAY"
    if canonical_market == "BTTS":
        if raw in {"YES", "Y", "BTTS_YES"}:
            return "BTTS_YES"
        if raw in {"NO", "N", "BTTS_NO"}:
            return "BTTS_NO"
    if canonical_market == "OVER_UNDER":
        if raw.startswith("OVER"):
            return "OVER"
        if raw.startswith("UNDER"):
            return "UNDER"
    raise MarketMappingError("SKIPPED_UNSUPPORTED_SELECTION", f"Unsupported selection for {market}: {selection}")


def extract_total_line(market: str | None, selection: str | None, explicit_line: object = None) -> Optional[Decimal]:
    explicit = to_decimal(explicit_line)
    if explicit is not None:
        return explicit
    for value in (selection, market):
        text = str(value or "")
        # Supports OVER_2_5, Over 2.5, OVER_UNDER_2_5, Total Goals 2.5.
        match = re.search(r"(\d+)(?:[._](\d+))?", text)
        if match:
            whole = match.group(1)
            frac = match.group(2)
            if frac is None:
                return Decimal(whole)
            return Decimal(f"{whole}.{frac}")
    return None


def is_supported_total_line(line: Decimal | None) -> bool:
    if line is None:
        return False
    # V25.1.3 deliberately supports whole and half lines only. Quarter/split lines
    # such as 2.25/2.75 are rejected until a later Asian-line settlement module exists.
    doubled = line * Decimal("2")
    return doubled == doubled.to_integral_value()


def normalize_pick_market_selection_line(market: str | None, selection: str | None, line: object = None) -> Tuple[str, str, Optional[Decimal]]:
    canonical_market = normalize_market(market)
    canonical_selection = normalize_selection(canonical_market, selection)
    total_line = None
    if canonical_market == "OVER_UNDER":
        total_line = extract_total_line(market, selection, line)
        if total_line is None:
            raise MarketMappingError("SKIPPED_MISSING_TOTAL_LINE", "Missing total-goals line for totals pick.")
        if not is_supported_total_line(total_line):
            raise MarketMappingError("SKIPPED_UNSUPPORTED_LINE", f"Unsupported totals line: {total_line}")
    return canonical_market, canonical_selection, total_line
