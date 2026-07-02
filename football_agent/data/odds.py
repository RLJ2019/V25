from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from collections import defaultdict
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from football_agent.config.loader import load_bookmaker_profiles
from football_agent.schemas import Competition, Fixture, OddsSnapshot


class BookmakerProfiler:
    def __init__(self, profiles: Optional[Dict] = None):
        self.profiles = profiles or load_bookmaker_profiles().get("bookmakers", {})

    def normalize_name(self, bookmaker: str) -> str:
        return bookmaker.lower().strip().replace(" ", "_").replace("-", "_")

    def profile(self, bookmaker: str) -> str:
        key = self.normalize_name(bookmaker)
        if key in self.profiles:
            return self.profiles[key].get("profile", "unknown")
        for k, v in self.profiles.items():
            label = self.normalize_name(v.get("label", ""))
            if key == label:
                return v.get("profile", "unknown")
        return "unknown"

    def enrich(self, odds: Iterable[OddsSnapshot]) -> List[OddsSnapshot]:
        out: List[OddsSnapshot] = []
        for o in odds:
            o.profile = self.profile(o.bookmaker)
            out.append(o)
        return out


@dataclass
class OddsDiscoveryMetrics:
    enabled: bool = False
    bulk_enabled: bool = True
    discovery_window_days: int = 14
    max_pages_per_query: int = 5
    max_requests: int = 80
    fixtures_scanned_total: int = 0
    fixtures_considered_for_odds: int = 0
    fixtures_skipped_no_api_id: int = 0
    fixtures_skipped_outside_window: int = 0
    bulk_queries: int = 0
    odds_requests: int = 0
    odds_pages_fetched: int = 0
    odds_results_zero: int = 0
    fixtures_with_odds: int = 0
    fixtures_without_odds: int = 0
    odds_rows_discovered: int = 0
    odds_rows_written: int = 0
    odds_provider_errors: int = 0
    selected_with_odds: int = 0
    selected_without_odds: int = 0
    request_limit_reached: bool = False

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class BulkOddsDiscoveryResult:
    odds_by_api_fixture_id: Dict[int, List[OddsSnapshot]]
    metrics: OddsDiscoveryMetrics


def _parse_iso_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        # API strings are ISO-like. The first 10 characters are stable for YYYY-MM-DD.
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def best_odds_by_selection(odds: Iterable[OddsSnapshot], prefer_profiles: Optional[List[str]] = None, allowed_markets: Optional[List[str]] = None) -> Dict[str, OddsSnapshot]:
    prefer_profiles = prefer_profiles or ["soft", "unknown", "semi-sharp", "sharp"]
    profile_rank = {p: i for i, p in enumerate(prefer_profiles)}
    best: Dict[str, OddsSnapshot] = {}
    for o in odds:
        if allowed_markets and o.market not in allowed_markets:
            continue
        current = best.get(o.selection)
        if current is None:
            best[o.selection] = o
            continue
        # Higher odds are better for the bettor. If equal, prefer desired profile order.
        if o.odds > current.odds or (o.odds == current.odds and profile_rank.get(o.profile, 9) < profile_rank.get(current.profile, 9)):
            best[o.selection] = o
    return best


def market_odds_matrix(odds: Iterable[OddsSnapshot], profile: Optional[str] = None, market: str = "1X2") -> Dict[str, float]:
    # Average odds per selection within a profile/market; useful for sharp baseline.
    buckets = defaultdict(list)
    for o in odds:
        if profile and o.profile != profile:
            continue
        if o.market == market and o.odds > 1:
            buckets[o.selection].append(o.odds)
    return {sel: sum(vals)/len(vals) for sel, vals in buckets.items() if vals}


class OddsDiscoveryService:
    """Bulk odds pre-filter for V25.1.2.

    V25.1.1 already inverted the funnel from fixture-first to odds-first, but it
    grouped bulk requests by league/date. V25.1.2 reduces API-call overhead by
    grouping discovery by league only and querying /odds?league=ID&season=YYYY
    with pagination guards. A local discovery window is still applied to candidate
    fixtures so far-future fixtures do not consume analysis slots.
    """

    def __init__(
        self,
        api_football_client,
        profiler: BookmakerProfiler,
        *,
        enabled: bool = True,
        bulk_enabled: bool = True,
        discovery_window_days: int = 14,
        max_pages_per_query: int = 5,
        max_requests: int = 80,
    ):
        self.api_football = api_football_client
        self.profiler = profiler
        self.enabled = enabled
        self.bulk_enabled = bulk_enabled
        self.discovery_window_days = max(0, int(discovery_window_days))
        self.max_pages_per_query = max(1, int(max_pages_per_query))
        self.max_requests = max(1, int(max_requests))

    def discover(
        self,
        fixtures: Sequence[Fixture],
        competitions_by_key: Mapping[str, Competition],
        *,
        season: int,
    ) -> BulkOddsDiscoveryResult:
        metrics = OddsDiscoveryMetrics(
            enabled=self.enabled,
            bulk_enabled=self.bulk_enabled,
            discovery_window_days=self.discovery_window_days,
            max_pages_per_query=self.max_pages_per_query,
            max_requests=self.max_requests,
            fixtures_scanned_total=len(fixtures),
        )
        odds_by_api_fixture_id: Dict[int, List[OddsSnapshot]] = {}

        if not self.enabled:
            print("Odds discovery overgeslagen: ODDS_DISCOVERY_ENABLED=false")
            return BulkOddsDiscoveryResult(odds_by_api_fixture_id, metrics)
        if not self.bulk_enabled:
            print("Odds discovery bulk overgeslagen: ODDS_DISCOVERY_BULK_ENABLED=false")
            return BulkOddsDiscoveryResult(odds_by_api_fixture_id, metrics)
        if not getattr(self.api_football, "enabled", False):
            print("Odds discovery overgeslagen: API-Football client disabled")
            return BulkOddsDiscoveryResult(odds_by_api_fixture_id, metrics)

        today = datetime.now(timezone.utc).date()
        max_future_date = today + timedelta(days=self.discovery_window_days)
        grouped: Dict[int, List[Fixture]] = defaultdict(list)
        considered_api_ids: set[int] = set()

        for fixture in fixtures:
            api_id = fixture.api_football_fixture_id
            if not api_id:
                metrics.fixtures_skipped_no_api_id += 1
                continue
            kickoff_date = _parse_iso_date(fixture.kickoff_utc)
            if kickoff_date is None:
                metrics.fixtures_skipped_outside_window += 1
                continue
            # Future odds are usually not available far ahead. Historical/test fixtures are
            # still allowed because they may have stored historical odds.
            if kickoff_date > max_future_date:
                metrics.fixtures_skipped_outside_window += 1
                continue
            comp = competitions_by_key.get(fixture.competition_key)
            league_id = comp.api_football_league_id if comp else None
            if not league_id:
                metrics.fixtures_skipped_no_api_id += 1
                continue
            grouped[int(league_id)].append(fixture)
            considered_api_ids.add(int(api_id))

        metrics.fixtures_considered_for_odds = len(considered_api_ids)
        metrics.bulk_queries = len(grouped)
        print(
            "Odds discovery start: fixtures_scanned={scanned} candidates={candidates} "
            "window_days={window} bulk_queries={queries} max_requests={max_req}".format(
                scanned=metrics.fixtures_scanned_total,
                candidates=metrics.fixtures_considered_for_odds,
                window=metrics.discovery_window_days,
                queries=metrics.bulk_queries,
                max_req=metrics.max_requests,
            )
        )

        for league_id in sorted(grouped.keys()):
            if metrics.odds_requests >= self.max_requests:
                metrics.request_limit_reached = True
                print("Odds discovery request-limit bereikt; resterende league queries overgeslagen.")
                break
            page = 1
            total_pages = 1
            while page <= total_pages and page <= self.max_pages_per_query:
                if metrics.odds_requests >= self.max_requests:
                    metrics.request_limit_reached = True
                    print("Odds discovery request-limit bereikt tijdens pagination.")
                    break
                try:
                    metrics.odds_requests += 1
                    data = self.api_football.odds_bulk(league_id=league_id, season=season, page=page)
                    metrics.odds_pages_fetched += 1
                    response = data.get("response", []) or []
                    results = int(data.get("results") or len(response) or 0)
                    paging = data.get("paging") or {}
                    try:
                        total_pages = int(paging.get("total") or 1)
                    except (TypeError, ValueError):
                        total_pages = 1
                    if results == 0 or not response:
                        metrics.odds_results_zero += 1
                    print(
                        "Bulk odds request: league={league} season={season} "
                        "page={page} results={results} total_pages={total}".format(
                            league=league_id,
                            season=season,
                            page=page,
                            results=results,
                            total=total_pages,
                        )
                    )
                    parsed = self.api_football.parse_odds_response(data)
                    for api_fixture_id, snapshots in parsed.items():
                        if api_fixture_id not in considered_api_ids:
                            continue
                        enriched = self.profiler.enrich(snapshots)
                        odds_by_api_fixture_id.setdefault(api_fixture_id, []).extend(enriched)
                    page += 1
                except Exception as exc:
                    metrics.odds_provider_errors += 1
                    print(f"Bulk odds ophalen faalde: league={league_id} season={season} page={page}: {exc}")
                    break

        metrics.fixtures_with_odds = sum(1 for api_id in considered_api_ids if odds_by_api_fixture_id.get(api_id))
        metrics.fixtures_without_odds = max(0, metrics.fixtures_considered_for_odds - metrics.fixtures_with_odds)
        metrics.odds_rows_discovered = sum(len(rows) for rows in odds_by_api_fixture_id.values())
        print(
            "Odds discovery result: fixtures_with_odds={with_odds} fixtures_without_odds={without_odds} "
            "odds_rows_discovered={rows} zero_result_requests={zero} provider_errors={errors}".format(
                with_odds=metrics.fixtures_with_odds,
                without_odds=metrics.fixtures_without_odds,
                rows=metrics.odds_rows_discovered,
                zero=metrics.odds_results_zero,
                errors=metrics.odds_provider_errors,
            )
        )
        return BulkOddsDiscoveryResult(odds_by_api_fixture_id, metrics)

    @staticmethod
    def select_with_odds_priority(
        fixtures: Sequence[Fixture],
        odds_by_api_fixture_id: Mapping[int, Sequence[OddsSnapshot]],
        *,
        max_matches: int,
    ) -> Tuple[List[Fixture], int, int]:
        with_odds: List[Fixture] = []
        without_odds: List[Fixture] = []
        for fixture in fixtures:
            api_id = fixture.api_football_fixture_id
            if api_id and odds_by_api_fixture_id.get(int(api_id)):
                with_odds.append(fixture)
            else:
                without_odds.append(fixture)
        selected = (with_odds + without_odds)[:max_matches]
        selected_with = sum(1 for fx in selected if fx.api_football_fixture_id and odds_by_api_fixture_id.get(int(fx.api_football_fixture_id)))
        selected_without = len(selected) - selected_with
        print(
            f"Selected for analysis: {len(selected)} | with_odds_priority={selected_with} "
            f"fallback_without_odds={selected_without} max_matches={max_matches}"
        )
        return selected, selected_with, selected_without
