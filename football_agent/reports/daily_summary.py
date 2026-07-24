from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable

from football_agent.schemas import PickDecision


_SUPPORTED_MARKETS = (
    "1X2",
    "BTTS",
    "OVER_UNDER_2_5",
)


def _market_counter() -> Dict[str, int]:
    return {
        market: 0
        for market in _SUPPORTED_MARKETS
    }


def _baseline_source_counter() -> Dict[str, Dict[str, int]]:
    return {
        market: {
            "sharp": 0,
            "all_bookmakers": 0,
        }
        for market in _SUPPORTED_MARKETS
    }


@dataclass
class IntegrityDiagnosticsMetrics:
    """Passive integrity observations for the daily run.

    These metrics report on the data already used by the agent. They do not
    alter probabilities, pick status, staking, exposure, notifications, or
    settlement behaviour.
    """

    fixtures_analyzed: int = 0
    fixtures_with_any_odds: int = 0
    fixtures_without_any_odds: int = 0
    odds_rows_analyzed: int = 0
    odds_fresh: int = 0
    odds_not_fresh: int = 0

    market_available: Dict[str, int] = field(
        default_factory=_market_counter
    )
    market_complete: Dict[str, int] = field(
        default_factory=_market_counter
    )
    market_incomplete: Dict[str, int] = field(
        default_factory=_market_counter
    )
    market_cleansing_success: Dict[str, int] = field(
        default_factory=_market_counter
    )
    market_cleansing_failed: Dict[str, int] = field(
        default_factory=_market_counter
    )
    baseline_source_counts: Dict[str, Dict[str, int]] = field(
        default_factory=_baseline_source_counter
    )
    reason_counts: Dict[str, int] = field(default_factory=dict)

    def record_reason(self, code: str, count: int = 1) -> None:
        if count <= 0:
            return
        self.reason_counts[code] = (
            self.reason_counts.get(code, 0) + int(count)
        )

    def observe_fixture(
        self,
        *,
        odds_count: int,
        odds_fresh: bool,
    ) -> None:
        count = max(0, int(odds_count))

        self.fixtures_analyzed += 1
        self.odds_rows_analyzed += count

        if count:
            self.fixtures_with_any_odds += 1
        else:
            self.fixtures_without_any_odds += 1
            self.record_reason("NO_ODDS_AVAILABLE")

        if odds_fresh:
            self.odds_fresh += 1
        else:
            self.odds_not_fresh += 1
            self.record_reason("ODDS_NOT_FRESH")

    def observe_market(
        self,
        *,
        market: str,
        available: bool,
        complete: bool,
        cleansing_attempted: bool,
        cleansing_succeeded: bool,
        baseline_source: str,
    ) -> None:
        # Defensive support for future diagnostic-only markets without making
        # observability capable of interrupting the production decision path.
        if market not in self.market_available:
            self.market_available[market] = 0
            self.market_complete[market] = 0
            self.market_incomplete[market] = 0
            self.market_cleansing_success[market] = 0
            self.market_cleansing_failed[market] = 0
            self.baseline_source_counts[market] = {
                "sharp": 0,
                "all_bookmakers": 0,
            }

        if not available:
            self.record_reason(f"{market}_NOT_AVAILABLE")
            return

        self.market_available[market] += 1

        source_counts = self.baseline_source_counts[market]
        source_counts[baseline_source] = (
            source_counts.get(baseline_source, 0) + 1
        )

        if complete:
            self.market_complete[market] += 1
        else:
            self.market_incomplete[market] += 1
            self.record_reason(f"{market}_INCOMPLETE")

        if not cleansing_attempted:
            return

        if cleansing_succeeded:
            self.market_cleansing_success[market] += 1
        else:
            self.market_cleansing_failed[market] += 1
            self.record_reason(f"{market}_CLEANSING_ERROR")

    def as_dict(self) -> Dict[str, object]:
        # dataclasses.asdict creates detached nested dictionaries.
        return asdict(self)


def _diagnostic_int(
    values: Dict[str, object],
    key: str,
) -> int:
    try:
        return int(values.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def build_operational_integrity_report(
    *,
    summary: Dict[str, object],
    integrity_diagnostics: Dict[str, object],
    odds_discovery: Dict[str, object],
) -> Dict[str, object]:
    """Build a compact, passive operational view of existing metrics.

    The report only reads values already produced by the daily pipeline. It
    does not alter picks, probabilities, staking, exposure, notifications, or
    settlement behaviour.
    """

    picks = {
        key: _diagnostic_int(summary, key)
        for key in (
            "scanned",
            "value_picks",
            "watchlist",
            "no_bet",
        )
    }

    market_incomplete = integrity_diagnostics.get(
        "market_incomplete",
        {},
    )
    if not isinstance(market_incomplete, dict):
        market_incomplete = {}

    market_cleansing_failed = integrity_diagnostics.get(
        "market_cleansing_failed",
        {},
    )
    if not isinstance(market_cleansing_failed, dict):
        market_cleansing_failed = {}

    baseline_source_counts = integrity_diagnostics.get(
        "baseline_source_counts",
        {},
    )
    if not isinstance(baseline_source_counts, dict):
        baseline_source_counts = {}

    incomplete_total = sum(
        _diagnostic_int(market_incomplete, market)
        for market in market_incomplete
    )
    cleansing_failed_total = sum(
        _diagnostic_int(market_cleansing_failed, market)
        for market in market_cleansing_failed
    )

    all_bookmakers_fallback_total = 0
    for source_counts in baseline_source_counts.values():
        if isinstance(source_counts, dict):
            all_bookmakers_fallback_total += _diagnostic_int(
                source_counts,
                "all_bookmakers",
            )

    integrity_reasons = integrity_diagnostics.get(
        "reason_counts",
        {},
    )
    if not isinstance(integrity_reasons, dict):
        integrity_reasons = {}

    discovery_reasons = odds_discovery.get(
        "reason_counts",
        {},
    )
    if not isinstance(discovery_reasons, dict):
        discovery_reasons = {}

    alerts = []

    if _diagnostic_int(integrity_diagnostics, "odds_not_fresh"):
        alerts.append("STALE_ODDS")

    if cleansing_failed_total:
        alerts.append("MARKET_CLEANSING_FAILURE")

    if _diagnostic_int(odds_discovery, "odds_provider_errors"):
        alerts.append("ODDS_PROVIDER_ERROR")

    if _diagnostic_int(odds_discovery, "selected_without_odds"):
        alerts.append("SELECTED_WITHOUT_ODDS")

    if bool(odds_discovery.get("request_limit_reached", False)):
        alerts.append("ODDS_REQUEST_LIMIT_REACHED")

    if _diagnostic_int(
        odds_discovery,
        "pagination_queries_truncated",
    ):
        alerts.append("ODDS_PAGINATION_TRUNCATED")

    investigate_alerts = set(alerts)

    if incomplete_total:
        alerts.append("INCOMPLETE_MARKETS")

    if all_bookmakers_fallback_total:
        alerts.append("ALL_BOOKMAKERS_FALLBACK_USED")

    if odds_discovery and odds_discovery.get("enabled") is False:
        alerts.append("ODDS_DISCOVERY_DISABLED")

    if odds_discovery and odds_discovery.get("bulk_enabled") is False:
        alerts.append("ODDS_DISCOVERY_BULK_DISABLED")

    if _diagnostic_int(discovery_reasons, "ODDS_PROVIDER_DISABLED"):
        alerts.append("ODDS_PROVIDER_DISABLED")

    if investigate_alerts:
        status = "INVESTIGATE"
    elif alerts:
        status = "OBSERVE"
    else:
        status = "HEALTHY"

    return {
        "status": status,
        "picks": picks,
        "fixtures": {
            "scanned_total": _diagnostic_int(
                odds_discovery,
                "fixtures_scanned_total",
            ),
            "considered_for_odds": _diagnostic_int(
                odds_discovery,
                "fixtures_considered_for_odds",
            ),
            "with_odds": _diagnostic_int(
                odds_discovery,
                "fixtures_with_odds",
            ),
            "without_odds": _diagnostic_int(
                odds_discovery,
                "fixtures_without_odds",
            ),
            "analyzed": _diagnostic_int(
                integrity_diagnostics,
                "fixtures_analyzed",
            ),
            "selected_with_odds": _diagnostic_int(
                odds_discovery,
                "selected_with_odds",
            ),
            "selected_without_odds": _diagnostic_int(
                odds_discovery,
                "selected_without_odds",
            ),
        },
        "odds": {
            "rows_discovered": _diagnostic_int(
                odds_discovery,
                "odds_rows_discovered",
            ),
            "rows_written": _diagnostic_int(
                odds_discovery,
                "odds_rows_written",
            ),
            "rows_analyzed": _diagnostic_int(
                integrity_diagnostics,
                "odds_rows_analyzed",
            ),
            "fresh": _diagnostic_int(
                integrity_diagnostics,
                "odds_fresh",
            ),
            "not_fresh": _diagnostic_int(
                integrity_diagnostics,
                "odds_not_fresh",
            ),
        },
        "markets": {
            "incomplete_total": incomplete_total,
            "cleansing_failed_total": cleansing_failed_total,
            "all_bookmakers_fallback_total": (
                all_bookmakers_fallback_total
            ),
        },
        "alerts": alerts,
        "reason_counts": {
            "integrity": dict(integrity_reasons),
            "odds_discovery": dict(discovery_reasons),
        },
    }

def summarize(picks: Iterable[PickDecision]) -> Dict:
    picks = list(picks)
    c = Counter(p.status for p in picks)
    return {
        "scanned": len(picks),
        "value_picks": c.get("VALUE_PICK", 0),
        "watchlist": c.get("WATCHLIST", 0),
        "no_bet": c.get("NO_BET", 0),
    }
