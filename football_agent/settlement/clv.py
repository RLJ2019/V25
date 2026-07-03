from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from football_agent.settlement.market_mapping import normalize_market, normalize_selection, extract_total_line


@dataclass(frozen=True)
class OddsQuote:
    bookmaker: str
    market: str
    selection: str
    odds: Decimal
    snapshot_id: Optional[str] = None
    captured_at: Optional[str] = None
    line: Optional[Decimal] = None


@dataclass(frozen=True)
class ClvResult:
    closing_odds: Optional[Decimal]
    closing_bookmaker: Optional[str]
    closing_snapshot_id: Optional[str]
    overround: Optional[Decimal]
    clv_market_movement: Optional[Decimal]
    clv_model_vs_close: Optional[Decimal]
    clv_method: str
    clv_warning: Optional[str] = None


def _dec(value: Any) -> Optional[Decimal]:
    try:
        if value is None or value == "":
            return None
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on", "ja"}


def benchmark_priority() -> List[str]:
    raw = os.getenv("CLV_BENCHMARK_BOOKMAKER_PRIORITY", "pinnacle,Pinnacle")
    values = [v.strip().lower().replace(" ", "_") for v in raw.split(",") if v.strip()]
    return values or ["pinnacle"]


def odds_quote_from_row(row: Mapping[str, Any]) -> Optional[OddsQuote]:
    odds = _dec(row.get("odds"))
    if odds is None or odds <= 0:
        return None
    market = str(row.get("market") or "")
    selection = str(row.get("selection") or "")
    line = _dec(row.get("line")) or extract_total_line(market, selection, None)
    return OddsQuote(
        bookmaker=str(row.get("bookmaker") or "unknown").lower().replace(" ", "_"),
        market=market,
        selection=selection,
        odds=odds,
        snapshot_id=str(row.get("snapshot_key") or row.get("snapshot_id") or "") or None,
        captured_at=str(row.get("captured_at") or row.get("snapshot_timestamp_utc") or "") or None,
        line=line,
    )


def _required_outcomes(market: str, line: Optional[Decimal] = None) -> List[str]:
    canonical = normalize_market(market)
    if canonical == "1X2":
        return ["HOME", "DRAW", "AWAY"]
    if canonical == "BTTS":
        return ["BTTS_YES", "BTTS_NO"]
    if canonical == "OVER_UNDER":
        return ["OVER", "UNDER"]
    return []


def _same_market_line(q: OddsQuote, market: str, line: Optional[Decimal]) -> bool:
    try:
        if normalize_market(q.market) != normalize_market(market):
            return False
    except Exception:
        return False
    if normalize_market(market) == "OVER_UNDER":
        return q.line is not None and line is not None and q.line == line
    return True


def _selection_key(q: OddsQuote, market: str) -> Optional[str]:
    try:
        return normalize_selection(normalize_market(market), q.selection)
    except Exception:
        return None


def _complete_bundle(quotes: Sequence[OddsQuote], market: str, line: Optional[Decimal], bookmaker: str) -> Optional[Dict[str, OddsQuote]]:
    required = set(_required_outcomes(market, line))
    if not required:
        return None
    bundle: Dict[str, OddsQuote] = {}
    bookmaker_norm = str(bookmaker or "").lower().replace(" ", "_")
    for quote in quotes:
        if quote.bookmaker != bookmaker_norm or not _same_market_line(quote, market, line):
            continue
        key = _selection_key(quote, market)
        if key in required:
            # If several rows exist, keep the last one passed in. Repository should
            # order by newest snapshot where possible.
            bundle[key] = quote
    return bundle if required.issubset(set(bundle)) else None


def _complete_bundles_by_bookmaker(quotes: Sequence[OddsQuote], market: str, line: Optional[Decimal]) -> Dict[str, Dict[str, OddsQuote]]:
    bookmakers = sorted({q.bookmaker for q in quotes if _same_market_line(q, market, line)})
    out: Dict[str, Dict[str, OddsQuote]] = {}
    for bookmaker in bookmakers:
        bundle = _complete_bundle(quotes, market, line, bookmaker)
        if bundle:
            out[bookmaker] = bundle
    return out


def _no_vig_probability(bundle: Mapping[str, OddsQuote], selected_key: str) -> tuple[Decimal, Decimal, Decimal]:
    selected = bundle[selected_key]
    implied = {key: Decimal("1") / quote.odds for key, quote in bundle.items()}
    overround = sum(implied.values(), Decimal("0"))
    if overround <= 0:
        raise ValueError("Invalid overround")
    return selected.odds, overround, implied[selected_key] / overround


def _median_consensus_probability(bundles: Mapping[str, Mapping[str, OddsQuote]], selected_key: str) -> tuple[Decimal, Decimal, Decimal, str]:
    probs: List[Decimal] = []
    overs: List[Decimal] = []
    selected_odds: List[Decimal] = []
    source_names: List[str] = []
    for bookmaker, bundle in bundles.items():
        odds, overround, prob = _no_vig_probability(bundle, selected_key)
        probs.append(prob)
        overs.append(overround)
        selected_odds.append(odds)
        source_names.append(bookmaker)
    if not probs:
        raise ValueError("No complete bundles for consensus")
    return Decimal(str(median(probs))), Decimal(str(median(overs))), Decimal(str(median(selected_odds))), ",".join(source_names)


def calculate_clv(
    *,
    entry_odds: Any,
    model_probability: Any,
    market: str,
    selection: str,
    line: Any = None,
    closing_bookmaker: Optional[str] = None,
    quotes: Iterable[OddsQuote | Mapping[str, Any]] = (),
) -> ClvResult:
    entry = _dec(entry_odds)
    model_prob = _dec(model_probability)
    total_line = _dec(line) or extract_total_line(market, selection, None)
    try:
        selected_key = normalize_selection(normalize_market(market), selection)
    except Exception:
        return ClvResult(None, None, None, None, None, None, "MISSING_CLOSING_ODDS", "UNSUPPORTED_MARKET_OR_SELECTION")
    quote_objs: List[OddsQuote] = []
    for quote in quotes:
        if isinstance(quote, OddsQuote):
            quote_objs.append(quote)
        else:
            parsed = odds_quote_from_row(quote)
            if parsed:
                quote_objs.append(parsed)

    if not quote_objs:
        return ClvResult(None, None, None, None, None, None, "MISSING_CLOSING_ODDS", "NO_CLOSING_QUOTES")

    def build_result(bundle: Mapping[str, OddsQuote], method: str, bookmaker: str) -> ClvResult:
        odds, overround, no_vig_prob = _no_vig_probability(bundle, selected_key)
        movement = (entry / odds - Decimal("1")) if entry and odds else None
        model_vs_close = (model_prob - no_vig_prob) if model_prob is not None else None
        quote = bundle[selected_key]
        return ClvResult(odds, bookmaker, quote.snapshot_id, overround, movement, model_vs_close, method)

    if closing_bookmaker:
        bundle = _complete_bundle(quote_objs, market, total_line, closing_bookmaker)
        if bundle:
            return build_result(bundle, "NO_VIG_SAME_BOOKMAKER", str(closing_bookmaker).lower().replace(" ", "_"))

    if _env_bool("CLV_ALLOW_BENCHMARK_FALLBACK", True):
        for bookmaker in benchmark_priority():
            bundle = _complete_bundle(quote_objs, market, total_line, bookmaker)
            if bundle:
                res = build_result(bundle, "NO_VIG_BENCHMARK_BOOKMAKER", bookmaker)
                return ClvResult(res.closing_odds, res.closing_bookmaker, res.closing_snapshot_id, res.overround, res.clv_market_movement, res.clv_model_vs_close, res.clv_method, "SAME_BOOKMAKER_INCOMPLETE")

    if _env_bool("CLV_ALLOW_CONSENSUS_FALLBACK", True):
        bundles = _complete_bundles_by_bookmaker(quote_objs, market, total_line)
        try:
            min_books = max(1, int(os.getenv("CLV_MIN_COMPLETE_BOOKMAKERS_FOR_CONSENSUS", "2")))
        except (TypeError, ValueError):
            min_books = 2
        if len(bundles) >= min_books:
            prob, overround, odds, source_names = _median_consensus_probability(bundles, selected_key)
            movement = (entry / odds - Decimal("1")) if entry and odds else None
            model_vs_close = (model_prob - prob) if model_prob is not None else None
            return ClvResult(odds, "consensus", None, overround, movement, model_vs_close, "NO_VIG_CONSENSUS_MARKET", f"CONSENSUS_BOOKMAKERS={source_names}")

    # Last resort: use selected odds only. Prefer same bookmaker selected quote, then
    # any matching selected quote. This keeps CLV available while clearly warning
    # that it is not no-vig.
    selected_quotes = [q for q in quote_objs if _same_market_line(q, market, total_line) and _selection_key(q, market) == selected_key]
    if closing_bookmaker:
        book = str(closing_bookmaker).lower().replace(" ", "_")
        selected_quotes = [q for q in selected_quotes if q.bookmaker == book] or selected_quotes
    if selected_quotes:
        q = selected_quotes[-1]
        implied = Decimal("1") / q.odds
        movement = (entry / q.odds - Decimal("1")) if entry else None
        model_vs_close = (model_prob - implied) if model_prob is not None else None
        return ClvResult(q.odds, q.bookmaker, q.snapshot_id, None, movement, model_vs_close, "IMPLIED_FALLBACK", "MISSING_COMPLEMENTARY_ODDS")

    return ClvResult(None, None, None, None, None, None, "MISSING_CLOSING_ODDS", "NO_SELECTED_CLOSING_ODDS")
