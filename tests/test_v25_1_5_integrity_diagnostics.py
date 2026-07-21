from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from football_agent.decision.exposure_manager import ExposureManager
from football_agent.decision.pick_selector import PickSelector
from football_agent.data.odds import BookmakerProfiler, OddsDiscoveryService
from football_agent.reports.daily_summary import (
    IntegrityDiagnosticsMetrics,
    summarize,
)
from football_agent.schemas import (
    Competition,
    FeatureAttribution,
    Fixture,
    MatchAnalysis,
    ModelProbabilities,
    OddsSnapshot,
    ValueDecision,
)


class _NoViolations:
    def violations(self, analysis, value):
        return []


class _FixedStaking:
    def recommend(self, **kwargs):
        return SimpleNamespace(
            raw_kelly_fraction=0.08,
            fractional_kelly=0.02,
            stake_units=0.50,
            reason="V25.1.4 characterization stake",
        )


class _FixedMarketAttributor:
    def attribute(self, analysis, value):
        return {"source": "V25.1.4-characterization"}


def _analysis(
    fixture_id: str,
    *,
    home_team: str,
    away_team: str,
) -> MatchAnalysis:
    fixture = Fixture(
        id=fixture_id,
        competition_key="eredivisie",
        competition_name="Eredivisie",
        home_team=home_team,
        away_team=away_team,
        kickoff_utc="2026-09-14T14:00:00Z",
    )
    attribution = FeatureAttribution(
        market_baseline=0.50,
        final_probability=0.60,
    )
    return MatchAnalysis(
        fixture=fixture,
        model_probabilities=ModelProbabilities(
            home=0.60,
            draw=0.22,
            away=0.18,
        ),
        market_probabilities={
            "HOME": 0.50,
            "DRAW": 0.28,
            "AWAY": 0.22,
        },
        attribution_home=attribution,
        attribution_draw=attribution,
        attribution_away=attribution,
        poisson=None,
        data_quality=9.0,
        confidence=9.0,
        risk_score=1.0,
        notes=["V25.1.4 characterization"],
        odds=[],
        market_cleansing_failed=False,
        market_probabilities_are_fallback=False,
        probability_intervals={"HOME": (0.55, 0.65)},
        uncertainty_score=2.0,
        data_snapshot_id="snapshot-characterization",
        time_window="FINAL",
        lineup_confirmed=True,
        odds_fresh=True,
    )


def _value(expected_value: float) -> ValueDecision:
    return ValueDecision(
        selection="HOME",
        model_probability=0.60,
        market_probability=0.50,
        odds=2.10,
        edge=expected_value,
        fair_odds=1.67,
        status="VALUE_CANDIDATE",
        reason="V25.1.4 characterization",
        bookmaker="pinnacle",
        probability_edge=0.10,
        expected_value=expected_value,
        market="1X2",
        baseline_source="sharp",
        sharp_market_probability=0.50,
        sharp_fair_odds=2.00,
        selected_odds_profile="sharp",
    )


def _fingerprint(pick):
    value = pick.value_decision
    return {
        "fixture_id": pick.fixture.id,
        "status": pick.status,
        "selection": pick.selection,
        "market": value.market if value else None,
        "bookmaker": value.bookmaker if value else None,
        "odds": value.odds if value else None,
        "model_probability": value.model_probability if value else None,
        "market_probability": value.market_probability if value else None,
        "edge": value.edge if value else None,
        "confidence": pick.confidence,
        "data_quality": pick.data_quality,
        "raw_kelly_fraction": pick.raw_kelly_fraction,
        "fractional_kelly": pick.fractional_kelly,
        "stake_units": pick.stake_units,
    }


class V2515IntegrityDiagnosticsCharacterizationTests(unittest.TestCase):
    def test_v2514_pick_and_stake_fingerprint_after_exposure(self):
        selector = PickSelector(
            no_bet_rules=_NoViolations(),
            staking=_FixedStaking(),
        )
        selector.market_attributor = _FixedMarketAttributor()

        first = selector.select(
            _analysis(
                "fx-characterization-1",
                home_team="PSV",
                away_team="Feyenoord",
            ),
            _value(0.26),
        )
        second = selector.select(
            _analysis(
                "fx-characterization-2",
                home_team="PSV",
                away_team="Ajax",
            ),
            _value(0.20),
        )

        managed = ExposureManager(
            max_value_picks_per_competition=3,
            max_value_picks_per_team=1,
            max_value_picks_per_fixture=1,
            max_total_units_per_day=3.0,
        ).apply([first, second])

        self.assertEqual(
            [_fingerprint(pick) for pick in managed],
            [
                {
                    "fixture_id": "fx-characterization-1",
                    "status": "VALUE_PICK",
                    "selection": "HOME",
                    "market": "1X2",
                    "bookmaker": "pinnacle",
                    "odds": 2.10,
                    "model_probability": 0.60,
                    "market_probability": 0.50,
                    "edge": 0.26,
                    "confidence": 9.0,
                    "data_quality": 9.0,
                    "raw_kelly_fraction": 0.08,
                    "fractional_kelly": 0.02,
                    "stake_units": 0.50,
                },
                {
                    "fixture_id": "fx-characterization-2",
                    "status": "WATCHLIST",
                    "selection": "HOME",
                    "market": "1X2",
                    "bookmaker": "pinnacle",
                    "odds": 2.10,
                    "model_probability": 0.60,
                    "market_probability": 0.50,
                    "edge": 0.20,
                    "confidence": 9.0,
                    "data_quality": 9.0,
                    "raw_kelly_fraction": 0.08,
                    "fractional_kelly": 0.0,
                    "stake_units": 0.0,
                },
            ],
        )

    def test_existing_daily_summary_contract_is_unchanged(self):
        selector = PickSelector(
            no_bet_rules=_NoViolations(),
            staking=_FixedStaking(),
        )
        selector.market_attributor = _FixedMarketAttributor()

        pick = selector.select(
            _analysis(
                "fx-summary-characterization",
                home_team="AZ",
                away_team="Twente",
            ),
            _value(0.26),
        )

        summary = summarize([pick])

        self.assertEqual(
            summary,
            {
                "scanned": 1,
                "value_picks": 1,
                "watchlist": 0,
                "no_bet": 0,
            },
        )
        self.assertEqual(
            set(summary),
            {"scanned", "value_picks", "watchlist", "no_bet"},
        )



class _ZeroResultsBulkOddsClient:
    enabled = True

    def __init__(self):
        self.calls = []

    def odds_bulk(
        self,
        *,
        league_id: int,
        season: int,
        odds_date=None,
        page: int = 1,
        **kwargs,
    ):
        self.calls.append((league_id, season, odds_date, page))
        return {
            "results": 0,
            "paging": {"current": page, "total": 1},
            "response": [],
        }

    def parse_odds_response(self, data):
        return {}


def _discovery_fixture(
    fixture_id: str,
    *,
    api_fixture_id,
    competition_key: str,
    kickoff_utc: str,
) -> Fixture:
    return Fixture(
        id=fixture_id,
        competition_key=competition_key,
        competition_name="Integrity League",
        home_team=f"Home {fixture_id}",
        away_team=f"Away {fixture_id}",
        kickoff_utc=kickoff_utc,
        source="api-football",
        api_football_fixture_id=api_fixture_id,
    )


class V2515OddsDiscoveryDiagnosticsTests(unittest.TestCase):
    def test_discovery_reason_split_preserves_legacy_aggregates(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        fixtures = [
            _discovery_fixture(
                "missing-fixture-api-id",
                api_fixture_id=None,
                competition_key="integrity",
                kickoff_utc=(now + timedelta(days=1)).isoformat(),
            ),
            _discovery_fixture(
                "invalid-kickoff",
                api_fixture_id=1002,
                competition_key="integrity",
                kickoff_utc="not-a-valid-kickoff",
            ),
            _discovery_fixture(
                "outside-window",
                api_fixture_id=1003,
                competition_key="integrity",
                kickoff_utc=(now + timedelta(days=30)).isoformat(),
            ),
            _discovery_fixture(
                "missing-league-api-id",
                api_fixture_id=1004,
                competition_key="missing_league",
                kickoff_utc=(now + timedelta(days=1)).isoformat(),
            ),
            _discovery_fixture(
                "valid-candidate",
                api_fixture_id=1005,
                competition_key="integrity",
                kickoff_utc=(now + timedelta(days=1)).isoformat(),
            ),
        ]
        competitions = {
            "integrity": Competition(
                key="integrity",
                name="Integrity League",
                country="Test",
                type="league",
                football_data_code=None,
                api_football_league_id=999,
            ),
            "missing_league": Competition(
                key="missing_league",
                name="Missing League ID",
                country="Test",
                type="league",
                football_data_code=None,
                api_football_league_id=None,
            ),
        }

        result = OddsDiscoveryService(
            _ZeroResultsBulkOddsClient(),
            BookmakerProfiler(
                profiles={"diagnostic": {"profile": "unknown"}}
            ),
            discovery_window_days=14,
            max_pages_per_query=2,
            max_requests=10,
        ).discover(fixtures, competitions, season=2026)

        metrics = result.metrics

        self.assertEqual(metrics.fixtures_skipped_missing_fixture_api_id, 1)
        self.assertEqual(metrics.fixtures_skipped_invalid_kickoff, 1)
        self.assertEqual(metrics.fixtures_skipped_future_window, 1)
        self.assertEqual(metrics.fixtures_skipped_missing_league_api_id, 1)

        # Bestaande V25.1.4 aggregaten blijven compatibel.
        self.assertEqual(metrics.fixtures_skipped_no_api_id, 2)
        self.assertEqual(metrics.fixtures_skipped_outside_window, 2)

        self.assertEqual(metrics.fixtures_considered_for_odds, 1)
        self.assertEqual(
            metrics.reason_counts,
            {
                "MISSING_FIXTURE_API_ID": 1,
                "INVALID_KICKOFF_UTC": 1,
                "OUTSIDE_DISCOVERY_WINDOW": 1,
                "MISSING_LEAGUE_API_ID": 1,
                "ODDS_PROVIDER_ZERO_RESULTS": 1,
                "NO_DISCOVERED_ODDS_FOR_FIXTURE": 1,
            },
        )

    def test_zero_provider_results_reports_fixture_without_discovered_odds(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        fixture = _discovery_fixture(
            "zero-results",
            api_fixture_id=2001,
            competition_key="integrity",
            kickoff_utc=(now + timedelta(days=1)).isoformat(),
        )
        competition = Competition(
            key="integrity",
            name="Integrity League",
            country="Test",
            type="league",
            football_data_code=None,
            api_football_league_id=999,
        )

        result = OddsDiscoveryService(
            _ZeroResultsBulkOddsClient(),
            BookmakerProfiler(
                profiles={"diagnostic": {"profile": "unknown"}}
            ),
            discovery_window_days=14,
            max_pages_per_query=2,
            max_requests=10,
        ).discover(
            [fixture],
            {"integrity": competition},
            season=2026,
        )

        self.assertEqual(result.metrics.odds_results_zero, 1)
        self.assertEqual(result.metrics.fixtures_without_odds, 1)
        self.assertEqual(
            result.metrics.reason_counts[
                "ODDS_PROVIDER_ZERO_RESULTS"
            ],
            1,
        )
        self.assertEqual(
            result.metrics.reason_counts[
                "NO_DISCOVERED_ODDS_FOR_FIXTURE"
            ],
            1,
        )


class _ProviderErrorBulkOddsClient:
    enabled = True

    def odds_bulk(self, **kwargs):
        raise RuntimeError("diagnostic provider failure")

    def parse_odds_response(self, data):
        raise AssertionError("Parser mag na provider failure niet worden aangeroepen.")


class _PaginatedMixedBulkOddsClient:
    enabled = True

    def __init__(self):
        self.calls = []

    def odds_bulk(
        self,
        *,
        league_id: int,
        season: int,
        odds_date=None,
        page: int = 1,
        **kwargs,
    ):
        self.calls.append((league_id, season, odds_date, page))
        return {
            "results": 2,
            "paging": {"current": page, "total": 3},
            "response": [
                {"fixture": {"id": 3001}},
                {"fixture": {"id": 9999}},
            ],
        }

    def parse_odds_response(self, data):
        return {
            3001: [
                OddsSnapshot(
                    bookmaker="diagnostic",
                    market="1X2",
                    selection="HOME",
                    odds=2.00,
                    timestamp_utc="2026-07-21T08:00:00Z",
                )
            ],
            9999: [
                OddsSnapshot(
                    bookmaker="diagnostic",
                    market="BTTS",
                    selection="BTTS_YES",
                    odds=1.80,
                    timestamp_utc="2026-07-21T08:00:00Z",
                ),
                OddsSnapshot(
                    bookmaker="diagnostic",
                    market="BTTS",
                    selection="BTTS_NO",
                    odds=2.00,
                    timestamp_utc="2026-07-21T08:00:00Z",
                ),
            ],
        }


class V2515OddsDiscoveryFailureDiagnosticsTests(unittest.TestCase):
    def test_provider_exception_is_reported_without_raising(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        fixture = _discovery_fixture(
            "provider-error",
            api_fixture_id=4001,
            competition_key="integrity",
            kickoff_utc=(now + timedelta(days=1)).isoformat(),
        )
        competition = Competition(
            key="integrity",
            name="Integrity League",
            country="Test",
            type="league",
            football_data_code=None,
            api_football_league_id=999,
        )

        result = OddsDiscoveryService(
            _ProviderErrorBulkOddsClient(),
            BookmakerProfiler(profiles={}),
            discovery_window_days=14,
            max_pages_per_query=2,
            max_requests=10,
        ).discover(
            [fixture],
            {"integrity": competition},
            season=2026,
        )

        self.assertEqual(result.metrics.odds_provider_errors, 1)
        self.assertEqual(result.metrics.fixtures_without_odds, 1)
        self.assertEqual(
            result.metrics.reason_counts,
            {
                "ODDS_PROVIDER_REQUEST_ERROR": 1,
                "NO_DISCOVERED_ODDS_FOR_FIXTURE": 1,
            },
        )

    def test_request_limit_reports_once_and_preserves_all_candidates(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        fixtures = [
            _discovery_fixture(
                "league-100",
                api_fixture_id=5001,
                competition_key="league_100",
                kickoff_utc=(now + timedelta(days=1)).isoformat(),
            ),
            _discovery_fixture(
                "league-200",
                api_fixture_id=5002,
                competition_key="league_200",
                kickoff_utc=(now + timedelta(days=1)).isoformat(),
            ),
        ]
        competitions = {
            "league_100": Competition(
                key="league_100",
                name="League 100",
                country="Test",
                type="league",
                football_data_code=None,
                api_football_league_id=100,
            ),
            "league_200": Competition(
                key="league_200",
                name="League 200",
                country="Test",
                type="league",
                football_data_code=None,
                api_football_league_id=200,
            ),
        }

        result = OddsDiscoveryService(
            _ZeroResultsBulkOddsClient(),
            BookmakerProfiler(profiles={}),
            discovery_window_days=14,
            max_pages_per_query=2,
            max_requests=1,
        ).discover(fixtures, competitions, season=2026)

        self.assertTrue(result.metrics.request_limit_reached)
        self.assertEqual(result.metrics.odds_requests, 1)
        self.assertEqual(result.metrics.fixtures_considered_for_odds, 2)
        self.assertEqual(result.metrics.fixtures_without_odds, 2)
        self.assertEqual(
            result.metrics.reason_counts[
                "ODDS_REQUEST_LIMIT_REACHED"
            ],
            1,
        )
        self.assertEqual(
            result.metrics.reason_counts[
                "NO_DISCOVERED_ODDS_FOR_FIXTURE"
            ],
            2,
        )

    def test_pagination_and_non_candidate_provider_rows_are_diagnostic_only(self):
        now = datetime.now(timezone.utc).replace(microsecond=0)
        fixture = _discovery_fixture(
            "candidate-3001",
            api_fixture_id=3001,
            competition_key="integrity",
            kickoff_utc=(now + timedelta(days=1)).isoformat(),
        )
        competition = Competition(
            key="integrity",
            name="Integrity League",
            country="Test",
            type="league",
            football_data_code=None,
            api_football_league_id=999,
        )

        result = OddsDiscoveryService(
            _PaginatedMixedBulkOddsClient(),
            BookmakerProfiler(
                profiles={"diagnostic": {"profile": "unknown"}}
            ),
            discovery_window_days=14,
            max_pages_per_query=1,
            max_requests=10,
        ).discover(
            [fixture],
            {"integrity": competition},
            season=2026,
        )

        metrics = result.metrics

        self.assertEqual(metrics.odds_requests, 1)
        self.assertEqual(metrics.provider_fixtures_returned, 2)
        self.assertEqual(
            metrics.provider_fixtures_ignored_not_considered,
            1,
        )
        self.assertEqual(metrics.odds_rows_ignored_not_considered, 2)
        self.assertEqual(metrics.pagination_queries_truncated, 1)
        self.assertEqual(metrics.fixtures_with_odds, 1)
        self.assertEqual(metrics.fixtures_without_odds, 0)
        self.assertEqual(metrics.odds_rows_discovered, 1)
        self.assertEqual(
            metrics.reason_counts,
            {"ODDS_PAGINATION_TRUNCATED": 1},
        )
        self.assertEqual(
            list(result.odds_by_api_fixture_id),
            [3001],
        )

class _DisabledProviderClient:
    enabled = False

    def odds_bulk(self, **kwargs):
        raise AssertionError(
            "Uitgeschakelde provider mag niet worden aangeroepen."
        )

    def parse_odds_response(self, data):
        raise AssertionError(
            "Parser mag bij uitgeschakelde provider niet worden aangeroepen."
        )


class _PartialFailureBulkOddsClient:
    enabled = True

    def __init__(self):
        self.calls = []

    def odds_bulk(
        self,
        *,
        league_id: int,
        season: int,
        odds_date=None,
        page: int = 1,
        **kwargs,
    ):
        self.calls.append((league_id, season, odds_date, page))
        if page == 2:
            raise RuntimeError("diagnostic failure on later page")

        return {
            "results": 1,
            "paging": {"current": page, "total": 2},
            "response": [
                {"fixture": {"id": 6001}},
            ],
        }

    def parse_odds_response(self, data):
        return {
            6001: [
                OddsSnapshot(
                    bookmaker="diagnostic",
                    market="1X2",
                    selection="HOME",
                    odds=2.00,
                    timestamp_utc="2026-07-21T08:00:00Z",
                ),
            ],
        }


class V2516OddsDiscoveryCoverageTests(unittest.TestCase):
    @staticmethod
    def _fixture_and_competition():
        now = datetime.now(timezone.utc).replace(microsecond=0)
        fixture = _discovery_fixture(
            "coverage-6001",
            api_fixture_id=6001,
            competition_key="integrity",
            kickoff_utc=(now + timedelta(days=1)).isoformat(),
        )
        competition = Competition(
            key="integrity",
            name="Integrity League",
            country="Test",
            type="league",
            football_data_code=None,
            api_football_league_id=999,
        )
        return fixture, competition

    def test_discovery_disabled_reports_reason_without_provider_calls(self):
        fixture, competition = self._fixture_and_competition()
        client = _ZeroResultsBulkOddsClient()

        result = OddsDiscoveryService(
            client,
            BookmakerProfiler(profiles={}),
            enabled=False,
            bulk_enabled=True,
        ).discover(
            [fixture],
            {"integrity": competition},
            season=2026,
        )

        self.assertEqual(client.calls, [])
        self.assertEqual(result.odds_by_api_fixture_id, {})
        self.assertEqual(
            result.metrics.reason_counts,
            {"ODDS_DISCOVERY_DISABLED": 1},
        )

    def test_bulk_disabled_reports_reason_without_provider_calls(self):
        fixture, competition = self._fixture_and_competition()
        client = _ZeroResultsBulkOddsClient()

        result = OddsDiscoveryService(
            client,
            BookmakerProfiler(profiles={}),
            enabled=True,
            bulk_enabled=False,
        ).discover(
            [fixture],
            {"integrity": competition},
            season=2026,
        )

        self.assertEqual(client.calls, [])
        self.assertEqual(result.odds_by_api_fixture_id, {})
        self.assertEqual(
            result.metrics.reason_counts,
            {"ODDS_DISCOVERY_BULK_DISABLED": 1},
        )

    def test_provider_disabled_reports_reason_without_requests(self):
        fixture, competition = self._fixture_and_competition()

        result = OddsDiscoveryService(
            _DisabledProviderClient(),
            BookmakerProfiler(profiles={}),
            enabled=True,
            bulk_enabled=True,
        ).discover(
            [fixture],
            {"integrity": competition},
            season=2026,
        )

        self.assertEqual(result.metrics.odds_requests, 0)
        self.assertEqual(result.odds_by_api_fixture_id, {})
        self.assertEqual(
            result.metrics.reason_counts,
            {"ODDS_PROVIDER_DISABLED": 1},
        )

    def test_later_page_failure_preserves_earlier_discovered_rows(self):
        fixture, competition = self._fixture_and_competition()
        client = _PartialFailureBulkOddsClient()

        result = OddsDiscoveryService(
            client,
            BookmakerProfiler(
                profiles={"diagnostic": {"profile": "unknown"}}
            ),
            enabled=True,
            bulk_enabled=True,
            discovery_window_days=14,
            max_pages_per_query=5,
            max_requests=10,
        ).discover(
            [fixture],
            {"integrity": competition},
            season=2026,
        )

        self.assertEqual(
            client.calls,
            [
                (999, 2026, None, 1),
                (999, 2026, None, 2),
            ],
        )
        self.assertEqual(result.metrics.odds_requests, 2)
        self.assertEqual(result.metrics.odds_pages_fetched, 1)
        self.assertEqual(result.metrics.odds_provider_errors, 1)
        self.assertEqual(result.metrics.fixtures_with_odds, 1)
        self.assertEqual(result.metrics.fixtures_without_odds, 0)
        self.assertEqual(result.metrics.odds_rows_discovered, 1)
        self.assertEqual(
            result.metrics.reason_counts,
            {"ODDS_PROVIDER_REQUEST_ERROR": 1},
        )
        self.assertEqual(
            list(result.odds_by_api_fixture_id),
            [6001],
        )

class V2515MarketIntegrityDiagnosticsTests(unittest.TestCase):
    def test_fixture_observation_counts_odds_and_freshness(self):
        metrics = IntegrityDiagnosticsMetrics()

        metrics.observe_fixture(
            odds_count=7,
            odds_fresh=True,
        )
        metrics.observe_fixture(
            odds_count=0,
            odds_fresh=False,
        )

        self.assertEqual(metrics.fixtures_analyzed, 2)
        self.assertEqual(metrics.fixtures_with_any_odds, 1)
        self.assertEqual(metrics.fixtures_without_any_odds, 1)
        self.assertEqual(metrics.odds_rows_analyzed, 7)
        self.assertEqual(metrics.odds_fresh, 1)
        self.assertEqual(metrics.odds_not_fresh, 1)
        self.assertEqual(
            metrics.reason_counts,
            {
                "NO_ODDS_AVAILABLE": 1,
                "ODDS_NOT_FRESH": 1,
            },
        )

    def test_market_observation_counts_complete_incomplete_and_missing(self):
        metrics = IntegrityDiagnosticsMetrics()

        metrics.observe_market(
            market="1X2",
            available=True,
            complete=True,
            cleansing_attempted=True,
            cleansing_succeeded=True,
            baseline_source="sharp",
        )
        metrics.observe_market(
            market="BTTS",
            available=True,
            complete=False,
            cleansing_attempted=False,
            cleansing_succeeded=False,
            baseline_source="all_bookmakers",
        )
        metrics.observe_market(
            market="OVER_UNDER_2_5",
            available=False,
            complete=False,
            cleansing_attempted=False,
            cleansing_succeeded=False,
            baseline_source="all_bookmakers",
        )

        self.assertEqual(
            metrics.market_available,
            {
                "1X2": 1,
                "BTTS": 1,
                "OVER_UNDER_2_5": 0,
            },
        )
        self.assertEqual(
            metrics.market_complete,
            {
                "1X2": 1,
                "BTTS": 0,
                "OVER_UNDER_2_5": 0,
            },
        )
        self.assertEqual(
            metrics.market_incomplete,
            {
                "1X2": 0,
                "BTTS": 1,
                "OVER_UNDER_2_5": 0,
            },
        )
        self.assertEqual(
            metrics.market_cleansing_success,
            {
                "1X2": 1,
                "BTTS": 0,
                "OVER_UNDER_2_5": 0,
            },
        )
        self.assertEqual(
            metrics.market_cleansing_failed,
            {
                "1X2": 0,
                "BTTS": 0,
                "OVER_UNDER_2_5": 0,
            },
        )
        self.assertEqual(
            metrics.baseline_source_counts,
            {
                "1X2": {
                    "sharp": 1,
                    "all_bookmakers": 0,
                },
                "BTTS": {
                    "sharp": 0,
                    "all_bookmakers": 1,
                },
                "OVER_UNDER_2_5": {
                    "sharp": 0,
                    "all_bookmakers": 0,
                },
            },
        )
        self.assertEqual(
            metrics.reason_counts,
            {
                "BTTS_INCOMPLETE": 1,
                "OVER_UNDER_2_5_NOT_AVAILABLE": 1,
            },
        )

    def test_complete_market_cleansing_failure_is_reported_separately(self):
        metrics = IntegrityDiagnosticsMetrics()

        metrics.observe_market(
            market="BTTS",
            available=True,
            complete=True,
            cleansing_attempted=True,
            cleansing_succeeded=False,
            baseline_source="all_bookmakers",
        )

        self.assertEqual(metrics.market_available["BTTS"], 1)
        self.assertEqual(metrics.market_complete["BTTS"], 1)
        self.assertEqual(metrics.market_incomplete["BTTS"], 0)
        self.assertEqual(metrics.market_cleansing_success["BTTS"], 0)
        self.assertEqual(metrics.market_cleansing_failed["BTTS"], 1)
        self.assertEqual(
            metrics.reason_counts,
            {"BTTS_CLEANSING_ERROR": 1},
        )


    def test_market_diagnostics_as_dict_is_detached_from_internal_state(self):
        metrics = IntegrityDiagnosticsMetrics()

        metrics.observe_fixture(
            odds_count=3,
            odds_fresh=True,
        )
        metrics.observe_market(
            market="1X2",
            available=True,
            complete=True,
            cleansing_attempted=True,
            cleansing_succeeded=True,
            baseline_source="sharp",
        )

        payload = metrics.as_dict()
        payload["reason_counts"]["MUTATED_EXTERNALLY"] = 99
        payload["market_available"]["1X2"] = 999

        self.assertNotIn(
            "MUTATED_EXTERNALLY",
            metrics.reason_counts,
        )
        self.assertEqual(
            metrics.market_available["1X2"],
            1,
        )

    def test_diagnostics_do_not_mutate_pick_fingerprint(self):
        selector = PickSelector(
            no_bet_rules=_NoViolations(),
            staking=_FixedStaking(),
        )
        selector.market_attributor = _FixedMarketAttributor()

        pick = selector.select(
            _analysis(
                "fx-diagnostics-non-mutation",
                home_team="PSV",
                away_team="Ajax",
            ),
            _value(0.26),
        )
        before = _fingerprint(pick)

        metrics = IntegrityDiagnosticsMetrics()
        metrics.observe_fixture(
            odds_count=3,
            odds_fresh=True,
        )
        metrics.observe_market(
            market="1X2",
            available=True,
            complete=True,
            cleansing_attempted=True,
            cleansing_succeeded=True,
            baseline_source="sharp",
        )
        metrics.as_dict()

        self.assertEqual(
            _fingerprint(pick),
            before,
        )


class V2515RunDailyInstrumentationTests(unittest.TestCase):
    def test_run_daily_integrity_diagnostics_are_observation_only(self):
        source = Path(
            "football_agent/scripts/run_daily.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "IntegrityDiagnosticsMetrics",
            source,
        )
        self.assertIn(
            "integrity_metrics = IntegrityDiagnosticsMetrics()",
            source,
        )
        self.assertEqual(
            source.count("integrity_metrics.observe_fixture("),
            1,
        )
        self.assertEqual(
            source.count("integrity_metrics.observe_market("),
            2,
        )

        analysis_start = source.index(
            "        analysis = ensemble.analyze("
        )
        pick_start = source.index(
            "        pick = selector.select(",
            analysis_start,
        )
        decision_path = source[analysis_start:pick_start]

        self.assertNotIn(
            "integrity_metrics",
            decision_path,
        )

        exposure_start = source.index(
            "    picks = exposure.apply(picks)"
        )
        summary_start = source.index(
            "    summary = summarize(picks)",
            exposure_start,
        )
        portfolio_path = source[exposure_start:summary_start]

        self.assertNotIn(
            "integrity_metrics",
            portfolio_path,
        )

        diagnostics_summary_line = (
            '    summary["integrity_diagnostics"] = '
            'integrity_metrics.as_dict()'
        )
        self.assertIn(
            diagnostics_summary_line,
            source,
        )

        diagnostics_summary_start = source.index(
            diagnostics_summary_line,
            summary_start,
        )
        daily_summary_write_start = source.index(
            '    (out_dir / "daily_summary.txt").write_text(',
            diagnostics_summary_start,
        )
        shadow_finish_start = source.index(
            "    shadow_db.finish(summary)",
            diagnostics_summary_start,
        )

        self.assertLess(
            summary_start,
            diagnostics_summary_start,
        )
        self.assertLess(
            diagnostics_summary_start,
            daily_summary_write_start,
        )
        self.assertLess(
            diagnostics_summary_start,
            shadow_finish_start,
        )

        diagnostics_summary_line = (
            '    summary["integrity_diagnostics"] = '
            'integrity_metrics.as_dict()'
        )
        self.assertIn(
            diagnostics_summary_line,
            source,
        )

        diagnostics_summary_start = source.index(
            diagnostics_summary_line,
            summary_start,
        )
        daily_summary_write_start = source.index(
            '    (out_dir / "daily_summary.txt").write_text(',
            diagnostics_summary_start,
        )
        shadow_finish_start = source.index(
            "    shadow_db.finish(summary)",
            diagnostics_summary_start,
        )

        self.assertLess(
            summary_start,
            diagnostics_summary_start,
        )
        self.assertLess(
            diagnostics_summary_start,
            daily_summary_write_start,
        )
        self.assertLess(
            diagnostics_summary_start,
            shadow_finish_start,
        )

if __name__ == "__main__":
    unittest.main()
