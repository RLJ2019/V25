from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
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
    closing_probability: Optional[Decimal]
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


def _parse_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _quote_sort_key(quote: OddsQuote) -> datetime:
    return _parse_utc(quote.captured_at) or datetime.min.replace(tzinfo=timezone.utc)


def _minute_key(value: Optional[str]) -> str:
    parsed = _parse_utc(value)
    if parsed is None:
        return "__undated__"
    return parsed.replace(second=0, microsecond=0).isoformat()


def _filter_quotes_for_kickoff(
    quotes: Sequence[OddsQuote],
    kickoff_utc: Optional[str],
) -> List[OddsQuote]:
    kickoff = _parse_utc(kickoff_utc)
    if kickoff is None:
        return list(quotes)

    eligible: List[OddsQuote] = []
    for quote in quotes:
        quote_time = _parse_utc(quote.captured_at)
        if quote_time is None:
            continue
        if quote_time <= kickoff:
            eligible.append(quote)
    return eligible


def odds_quote_from_row(row: Mapping[str, Any]) -> Optional[OddsQuote]:
    odds = _dec(row.get("odds"))
    if odds is None or odds <= Decimal("1"):
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
        captured_at=str(row.get("snapshot_timestamp_utc") or row.get("captured_at") or "") or None,
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


def _complete_bundle(
    quotes: Sequence[OddsQuote],
    market: str,
    line: Optional[Decimal],
    bookmaker: str,
) -> Optional[Dict[str, OddsQuote]]:
    required = set(_required_outcomes(market, line))
    if not required:
        return None

    bookmaker_norm = str(bookmaker or "").lower().replace(" ", "_")
    bundles_by_minute: Dict[str, Dict[str, OddsQuote]] = {}

    for quote in quotes:
        if quote.bookmaker != bookmaker_norm:
            continue
        if not _same_market_line(quote, market, line):
            continue

        selection_key = _selection_key(quote, market)
        if selection_key not in required:
            continue

        minute = _minute_key(quote.captured_at)
        bundle = bundles_by_minute.setdefault(minute, {})
        current = bundle.get(selection_key)

        # Binnen dezelfde provider-minuut behouden we de nieuwste observatie.
        if current is None or _quote_sort_key(quote) >= _quote_sort_key(current):
            bundle[selection_key] = quote

    complete_bundles = [
        bundle
        for bundle in bundles_by_minute.values()
        if required.issubset(set(bundle))
    ]
    if not complete_bundles:
        return None

    # Kies de nieuwste complete bundle. Een incomplete nieuwere minuut mag een
    # oudere complete closing bundle dus niet overschrijven.
    return max(
        complete_bundles,
        key=lambda bundle: max(
            (_quote_sort_key(quote) for quote in bundle.values()),
            default=datetime.min.replace(tzinfo=timezone.utc),
        ),
    )

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
    kickoff_utc: Optional[str] = None,
    closing_bookmaker: Optional[str] = None,
    quotes: Iterable[OddsQuote | Mapping[str, Any]] = (),
) -> ClvResult:
    entry = _dec(entry_odds)
    model_prob = _dec(model_probability)
    total_line = _dec(line) or extract_total_line(market, selection, None)

    try:
        selected_key = normalize_selection(normalize_market(market), selection)
    except Exception:
        return ClvResult(
            closing_odds=None,
            closing_bookmaker=None,
            closing_snapshot_id=None,
            overround=None,
            closing_probability=None,
            clv_market_movement=None,
            clv_model_vs_close=None,
            clv_method="MISSING_CLOSING_ODDS",
            clv_warning="UNSUPPORTED_MARKET_OR_SELECTION",
        )

    quote_objs: List[OddsQuote] = []
    for quote in quotes:
        if isinstance(quote, OddsQuote):
            quote_odds = _dec(quote.odds)
            if quote_odds is None or quote_odds <= Decimal("1"):
                continue
            quote_objs.append(quote)
        else:
            parsed = odds_quote_from_row(quote)
            if parsed:
                quote_objs.append(parsed)

    # Alleen providerquotes op of vóór de oorspronkelijke kickoff mogen als
    # closing odds worden gebruikt.
    quote_objs = _filter_quotes_for_kickoff(quote_objs, kickoff_utc)

    if not quote_objs:
        return ClvResult(
            closing_odds=None,
            closing_bookmaker=None,
            closing_snapshot_id=None,
            overround=None,
            closing_probability=None,
            clv_market_movement=None,
            clv_model_vs_close=None,
            clv_method="MISSING_CLOSING_ODDS",
            clv_warning="NO_CLOSING_QUOTES",
        )

    def build_result(
        bundle: Mapping[str, OddsQuote],
        method: str,
        bookmaker: str,
    ) -> ClvResult:
        odds, overround, no_vig_probability = _no_vig_probability(
            bundle,
            selected_key,
        )
        movement = (
            entry / odds - Decimal("1")
            if entry is not None and odds is not None
            else None
        )
        model_vs_close = (
            model_prob - no_vig_probability
            if model_prob is not None
            else None
        )
        selected_quote = bundle[selected_key]

        return ClvResult(
            closing_odds=odds,
            closing_bookmaker=bookmaker,
            closing_snapshot_id=selected_quote.snapshot_id,
            overround=overround,
            closing_probability=no_vig_probability,
            clv_market_movement=movement,
            clv_model_vs_close=model_vs_close,
            clv_method=method,
        )

    if closing_bookmaker:
        bundle = _complete_bundle(
            quote_objs,
            market,
            total_line,
            closing_bookmaker,
        )
        if bundle:
            return build_result(
                bundle,
                "NO_VIG_SAME_BOOKMAKER",
                str(closing_bookmaker).lower().replace(" ", "_"),
            )

    if _env_bool("CLV_ALLOW_BENCHMARK_FALLBACK", True):
        for bookmaker in benchmark_priority():
            bundle = _complete_bundle(
                quote_objs,
                market,
                total_line,
                bookmaker,
            )
            if bundle:
                result = build_result(
                    bundle,
                    "NO_VIG_BENCHMARK_BOOKMAKER",
                    bookmaker,
                )
                return ClvResult(
                    closing_odds=result.closing_odds,
                    closing_bookmaker=result.closing_bookmaker,
                    closing_snapshot_id=result.closing_snapshot_id,
                    overround=result.overround,
                    closing_probability=result.closing_probability,
                    clv_market_movement=result.clv_market_movement,
                    clv_model_vs_close=result.clv_model_vs_close,
                    clv_method=result.clv_method,
                    clv_warning="SAME_BOOKMAKER_INCOMPLETE",
                )

    if _env_bool("CLV_ALLOW_CONSENSUS_FALLBACK", True):
        bundles = _complete_bundles_by_bookmaker(
            quote_objs,
            market,
            total_line,
        )
        try:
            min_books = max(
                1,
                int(
                    os.getenv(
                        "CLV_MIN_COMPLETE_BOOKMAKERS_FOR_CONSENSUS",
                        "2",
                    )
                ),
            )
        except (TypeError, ValueError):
            min_books = 2

        if len(bundles) >= min_books:
            probability, overround, odds, source_names = (
                _median_consensus_probability(
                    bundles,
                    selected_key,
                )
            )
            movement = (
                entry / odds - Decimal("1")
                if entry is not None and odds is not None
                else None
            )
            model_vs_close = (
                model_prob - probability
                if model_prob is not None
                else None
            )

            return ClvResult(
                closing_odds=odds,
                closing_bookmaker="consensus",
                closing_snapshot_id=None,
                overround=overround,
                closing_probability=probability,
                clv_market_movement=movement,
                clv_model_vs_close=model_vs_close,
                clv_method="NO_VIG_CONSENSUS_MARKET",
                clv_warning=f"CONSENSUS_BOOKMAKERS={source_names}",
            )

    # Alleen wanneer geen complete markt-bundle beschikbaar is, gebruiken we
    # de selected-odds implied probability als expliciet gelabelde fallback.
    selected_quotes = [
        quote
        for quote in quote_objs
        if _same_market_line(quote, market, total_line)
        and _selection_key(quote, market) == selected_key
    ]

    if closing_bookmaker:
        bookmaker = str(closing_bookmaker).lower().replace(" ", "_")
        same_bookmaker_quotes = [
            quote
            for quote in selected_quotes
            if quote.bookmaker == bookmaker
        ]
        selected_quotes = same_bookmaker_quotes or selected_quotes

    if selected_quotes:
        selected_quotes.sort(key=_quote_sort_key)
        quote = selected_quotes[-1]
        implied_probability = Decimal("1") / quote.odds
        movement = (
            entry / quote.odds - Decimal("1")
            if entry is not None
            else None
        )
        model_vs_close = (
            model_prob - implied_probability
            if model_prob is not None
            else None
        )

        return ClvResult(
            closing_odds=quote.odds,
            closing_bookmaker=quote.bookmaker,
            closing_snapshot_id=quote.snapshot_id,
            overround=None,
            closing_probability=implied_probability,
            clv_market_movement=movement,
            clv_model_vs_close=model_vs_close,
            clv_method="IMPLIED_FALLBACK",
            clv_warning="MISSING_COMPLEMENTARY_ODDS",
        )

    return ClvResult(
        closing_odds=None,
        closing_bookmaker=None,
        closing_snapshot_id=None,
        overround=None,
        closing_probability=None,
        clv_market_movement=None,
        clv_model_vs_close=None,
        clv_method="MISSING_CLOSING_ODDS",
        clv_warning="NO_SELECTED_CLOSING_ODDS",
    )
