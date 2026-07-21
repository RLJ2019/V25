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


def summarize(picks: Iterable[PickDecision]) -> Dict:
    picks = list(picks)
    c = Counter(p.status for p in picks)
    return {
        "scanned": len(picks),
        "value_picks": c.get("VALUE_PICK", 0),
        "watchlist": c.get("WATCHLIST", 0),
        "no_bet": c.get("NO_BET", 0),
    }
