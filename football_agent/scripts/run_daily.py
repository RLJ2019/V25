from __future__ import annotations

import os
from pathlib import Path
from typing import List
from datetime import date

from football_agent.data.fixtures import FixtureProvider
from football_agent.data.api_football import ApiFootballClient
from football_agent.data.odds import BookmakerProfiler, OddsDiscoveryService, best_odds_by_selection, market_odds_matrix
from football_agent.models.market_model import MarketModel
from football_agent.models.ensemble import EnsembleModel
from football_agent.models.value_engine import ValueEngine
from football_agent.decision.no_bet_rules import NoBetRules
from football_agent.decision.pick_selector import PickSelector
from football_agent.decision.exposure_manager import ExposureManager
from football_agent.decision.staking import FractionalKellyStaking
from football_agent.storage.prediction_log import PredictionLog
from football_agent.storage.odds_snapshots import OddsSnapshotStore
from football_agent.storage.data_snapshots import DataSnapshotStore
from football_agent.storage.odds_timeline import OddsTimelineAnalyzer
from football_agent.reports.telegram import TelegramReporter
from football_agent.reports.daily_summary import (
    IntegrityDiagnosticsMetrics,
    summarize,
)
from football_agent.storage.model_versions import MODEL_VERSION
from football_agent.storage.notification_state import NotificationState
from football_agent.reports.live_sheet_export import LiveSheetExporter
from football_agent.utils_time import time_window_for_fixture, minutes_until
from football_agent.models.calendar_context import InternationalBreakFilter
from football_agent.database.shadow_writer import ShadowDatabaseWriter
from football_agent.config.loader import load_competitions


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "ja"}


def _is_lineup_monitor_runtime(run_type: str, only_lineup_window: bool) -> bool:
    normalized = (run_type or "").strip().lower().replace("_", "-")
    return bool(only_lineup_window or normalized == "lineup-monitor")


def _configured_fixture_season() -> int:
    config = load_competitions()
    default = int(config.get("season", date.today().year))
    raw = os.getenv("FIXTURE_SEASON", "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _norm_team(name: str) -> str:
    return " ".join((name or "").lower().replace(".", "").split())

def _is_promoted(team: str, promoted_teams: list[str]) -> bool:
    t = _norm_team(team)
    return any(t == _norm_team(p) or t in _norm_team(p) or _norm_team(p) in t for p in promoted_teams)


def main() -> None:
    out_dir = Path(os.getenv("LOCAL_OUTPUT_DIR", "output"))
    out_dir.mkdir(parents=True, exist_ok=True)
    run_type = os.getenv("AGENT_RUN_TYPE", "daily").strip() or "daily"
    shadow_db = ShadowDatabaseWriter(out_dir, run_type)
    shadow_db.begin({"model_version": MODEL_VERSION})
    days_ahead = _env_int("DAYS_AHEAD", 7)
    max_matches = _env_int("MAX_MATCHES", 80)
    min_edge = _env_float("MIN_EDGE", 0.04)
    min_data = _env_float("MIN_DATA_QUALITY", 7.0)
    min_conf = _env_float("MIN_CONFIDENCE", 7.0)
    require_odds = _bool("REQUIRE_ODDS_FOR_VALUE_PICK", True)
    max_odds_age_minutes = _env_int("MAX_ODDS_AGE_MINUTES", 180)
    require_final_lineup = _bool("REQUIRE_FINAL_LINEUP_FOR_VALUE_PICK", True)
    international_break_days_after = _env_int("INTERNATIONAL_BREAK_DAYS_AFTER", 7)
    kelly_fraction = _env_float("KELLY_FRACTION", 0.15)
    bankroll_units = _env_float("BANKROLL_UNITS", 100.0)
    max_units_per_pick = _env_float("MAX_UNITS_PER_PICK", 2.0)
    min_units_for_value = _env_float("MIN_UNITS_FOR_VALUE_PICK", 0.25)
    max_total_units_per_day = _env_float("MAX_TOTAL_UNITS_PER_DAY", 3.0)
    send_daily_report = _bool("SEND_DAILY_REPORT", True)
    send_value_alerts = _bool("SEND_VALUE_ALERTS", True)
    send_heartbeat = _bool("SEND_HEARTBEAT", True)
    only_lineup_window = _bool("ONLY_LINEUP_WINDOW", False)
    only_watchlist_lineup_monitor = _bool("ONLY_WATCHLIST_LINEUP_MONITOR", False)
    lineup_window_start = _env_int("LINEUP_WINDOW_START_MINUTES", 65)
    lineup_window_end = _env_int("LINEUP_WINDOW_END_MINUTES", 45)
    heartbeat_min_hour_utc = _env_int("HEARTBEAT_MIN_HOUR_UTC", 17)
    odds_discovery_enabled = _bool("ODDS_DISCOVERY_ENABLED", True)
    odds_discovery_bulk_enabled = _bool("ODDS_DISCOVERY_BULK_ENABLED", True)
    odds_discovery_days = _env_int("ODDS_DISCOVERY_DAYS", 14)
    odds_discovery_scan_limit = _env_int("ODDS_DISCOVERY_SCAN_LIMIT", max(max_matches, 250))
    odds_discovery_max_pages = _env_int("ODDS_DISCOVERY_MAX_PAGES", 5)
    odds_discovery_max_requests = _env_int("ODDS_DISCOVERY_MAX_REQUESTS", 80)

    if _is_lineup_monitor_runtime(run_type, only_lineup_window):
        if odds_discovery_enabled or odds_discovery_bulk_enabled:
            print(
                "Odds discovery disabled for line-up monitor; "
                "using real-time fixture odds fallback for closing-line validation."
            )
        odds_discovery_enabled = False
        odds_discovery_bulk_enabled = False

    fixture_season = _configured_fixture_season()

    print(f"V25 agent start: {MODEL_VERSION}")
    print(
        "DAYS_AHEAD={days} MAX_MATCHES={mx} MIN_EDGE={edge} MIN_DATA={data} "
        "MIN_CONF={conf} REQUIRE_ODDS={odds} MAX_ODDS_AGE={age} REQUIRE_FINAL_LINEUP={lineup}".format(
            days=days_ahead,
            mx=max_matches,
            edge=min_edge,
            data=min_data,
            conf=min_conf,
            odds=require_odds,
            age=max_odds_age_minutes,
            lineup=require_final_lineup,
        )
    )
    print(
        "ODDS_DISCOVERY enabled={enabled} bulk={bulk} window_days={days} "
        "scan_limit={scan_limit} max_pages={pages} max_requests={requests}".format(
            enabled=odds_discovery_enabled,
            bulk=odds_discovery_bulk_enabled,
            days=odds_discovery_days,
            scan_limit=odds_discovery_scan_limit,
            pages=odds_discovery_max_pages,
            requests=odds_discovery_max_requests,
        )
    )

    fixture_provider = FixtureProvider()
    competitions = fixture_provider.competitions()
    competition_by_key = {c.key: c for c in competitions}
    print("Actieve competities:", ", ".join(c.name for c in competitions))
    # V25.1.1 scans wider than MAX_MATCHES, discovers bulk odds, then selects the
    # final MAX_MATCHES with odds priority. This protects analysis slots from being
    # spent on qualification fixtures whose bookmaker markets are not open yet.
    scan_limit = odds_discovery_scan_limit if odds_discovery_enabled else max_matches
    fixtures = fixture_provider.upcoming(days_ahead=days_ahead, max_matches=scan_limit)
    if only_lineup_window:
        active_ids: set[str] | None = None
        if only_watchlist_lineup_monitor:
            active_ids = NotificationState(out_dir / "notification_state.json").active_fixture_ids({"WATCHLIST", "VALUE_PICK"})
        filtered = []
        for fx in fixtures:
            mins = minutes_until(fx.kickoff_utc)
            in_lineup_window = mins is not None and lineup_window_end <= mins <= lineup_window_start
            if not in_lineup_window:
                continue
            if active_ids is not None and active_ids and str(fx.id) not in active_ids:
                continue
            filtered.append(fx)
        fixtures = filtered
        scope = "watchlist/value only" if only_watchlist_lineup_monitor else "all fixtures"
        print(f"Line-up monitor actief: T-{lineup_window_start} t/m T-{lineup_window_end} minuten | scope={scope} | wedstrijden in window: {len(fixtures)}")
    print(f"Wedstrijden gevonden vóór odds-selectie: {len(fixtures)}")

    api_football = ApiFootballClient()
    profiler = BookmakerProfiler()
    odds_by_api_fixture_id = {}
    odds_metrics = {}
    if odds_discovery_enabled:
        odds_discovery = OddsDiscoveryService(
            api_football,
            profiler,
            enabled=odds_discovery_enabled,
            bulk_enabled=odds_discovery_bulk_enabled,
            discovery_window_days=odds_discovery_days,
            max_pages_per_query=odds_discovery_max_pages,
            max_requests=odds_discovery_max_requests,
        )
        discovery_result = odds_discovery.discover(fixtures, competition_by_key, season=fixture_season)
        odds_by_api_fixture_id = discovery_result.odds_by_api_fixture_id
        fixtures, selected_with_odds, selected_without_odds = OddsDiscoveryService.select_with_odds_priority(
            fixtures, odds_by_api_fixture_id, max_matches=max_matches
        )
        discovery_result.metrics.selected_with_odds = selected_with_odds
        discovery_result.metrics.selected_without_odds = selected_without_odds
        odds_metrics = discovery_result.metrics.as_dict()
    else:
        fixtures = fixtures[:max_matches]
        print(f"Odds discovery uitgeschakeld; eerste {len(fixtures)} fixtures geselecteerd.")

    print(f"Wedstrijden geselecteerd voor analyse: {len(fixtures)}")

    standings_by_comp = {}
    fixture_comp_keys = {fixture.competition_key for fixture in fixtures}
    if fixtures and fixture_provider.football_data.enabled:
        print("Standings ophalen voor competities met fixtures:", ", ".join(sorted(fixture_comp_keys)))
        for comp in competitions:
            if comp.key not in fixture_comp_keys:
                continue
            if not comp.football_data_code:
                print(f"Standings overgeslagen voor {comp.name}: geen football_data_code")
                continue
            try:
                table = fixture_provider.football_data.standings_table(comp)
                if table:
                    standings_by_comp[comp.key] = table
                    print(f"Standings opgehaald voor {comp.name}")
                else:
                    print(f"Geen standings ontvangen voor {comp.name}")
            except Exception as exc:
                print(f"Standen ophalen faalde voor {comp.name}: {exc}")
    else:
        print("Geen fixtures gevonden; standings ophalen overgeslagen.")

    market = MarketModel()
    ensemble = EnsembleModel()
    value_engine = ValueEngine(min_edge=min_edge)
    selector = PickSelector(
        NoBetRules(
            require_odds=require_odds,
            min_data_quality=min_data,
            min_confidence=min_conf,
            require_final_lineup=require_final_lineup,
            min_stake_units_for_value=min_units_for_value,
        ),
        staking=FractionalKellyStaking(
            kelly_fraction=kelly_fraction,
            bankroll_units=bankroll_units,
            max_units_per_pick=max_units_per_pick,
            min_units_for_value=min_units_for_value,
        ),
    )
    exposure = ExposureManager(
        max_value_picks_per_competition=_env_int("MAX_VALUE_PICKS_PER_COMPETITION", 3),
        max_value_picks_per_team=_env_int("MAX_VALUE_PICKS_PER_TEAM", 1),
        max_value_picks_per_fixture=_env_int("MAX_VALUE_PICKS_PER_FIXTURE", 1),
        max_total_units_per_day=max_total_units_per_day,
    )
    odds_timeline = OddsTimelineAnalyzer(max_age_minutes=max_odds_age_minutes)
    international_break_filter = InternationalBreakFilter(days_after=international_break_days_after)
    integrity_metrics = IntegrityDiagnosticsMetrics()

    prediction_log = PredictionLog(out_dir / "prediction_log.csv")
    odds_store = OddsSnapshotStore(out_dir / "odds_snapshots.csv")
    data_snapshots = DataSnapshotStore(out_dir)
    notification_state = NotificationState(out_dir / "notification_state.json")
    live_sheet = LiveSheetExporter(out_dir / "live_picks_sheet.csv")

    picks = []
    shadow_observations = []
    for fixture in fixtures:
        odds = []
        lineups = []
        time_window = time_window_for_fixture(fixture.kickoff_utc)
        post_international_break = international_break_filter.is_post_break_fixture(fixture.kickoff_utc)
        if fixture.api_football_fixture_id and api_football.enabled:
            if odds_discovery_enabled and odds_discovery_bulk_enabled:
                odds = list(odds_by_api_fixture_id.get(int(fixture.api_football_fixture_id), []))
            else:
                try:
                    odds = profiler.enrich(api_football.odds(fixture.api_football_fixture_id))
                except Exception as exc:
                    print(f"Odds ophalen faalde voor {fixture.matchup}: {exc}")
            if time_window == "FINAL":
                try:
                    lineups = api_football.lineups(fixture.api_football_fixture_id)
                except Exception as exc:
                    print(f"Line-ups ophalen faalde voor {fixture.matchup}: {exc}")
        odds_store.append(fixture, odds)
        shadow_observations.append((fixture, list(odds)))
        freshness = odds_timeline.freshness(odds)
        sharp_movement = odds_timeline.sharp_implied_movement(odds)
        integrity_metrics.observe_fixture(
            odds_count=len(odds),
            odds_fresh=freshness.fresh,
        )

        sharp_odds = market_odds_matrix(odds, profile="sharp", market="1X2")
        all_odds = market_odds_matrix(odds, market="1X2")
        one_x_two_has_sharp = all(k in sharp_odds for k in ["HOME", "DRAW", "AWAY"])
        odds_for_market = sharp_odds if one_x_two_has_sharp else all_odds
        baseline_source_by_market = {"1X2": "sharp" if one_x_two_has_sharp else "all_bookmakers"}
        one_x_two_complete = all(
            key in odds_for_market
            for key in ["HOME", "DRAW", "AWAY"]
        )
        one_x_two_cleansing_succeeded = False
        market_cleansing_failed = False
        if one_x_two_complete:
            try:
                market_probs = market.no_vig_probabilities(odds_for_market)
                one_x_two_cleansing_succeeded = True
            except Exception as exc:
                print(f"Market cleansing faalde voor {fixture.matchup}: {exc}")
                market_probs = None
                market_cleansing_failed = True
        else:
            market_probs = None
            market_cleansing_failed = bool(odds)

        integrity_metrics.observe_market(
            market="1X2",
            available=bool(odds_for_market),
            complete=one_x_two_complete,
            cleansing_attempted=one_x_two_complete,
            cleansing_succeeded=one_x_two_cleansing_succeeded,
            baseline_source=baseline_source_by_market["1X2"],
        )

        # Build value-market probabilities for 1X2 plus goal markets when odds exist.
        # The 1X2 market remains the anchor for the ensemble baseline; extra markets are
        # only used by the ValueEngine.
        value_market_probs = dict(market_probs or {})
        extra_market_selections = {
            "OVER_UNDER_2_5": {"OVER_2_5", "UNDER_2_5"},
            "BTTS": {"BTTS_YES", "BTTS_NO"},
        }
        for extra_market, required_selections in extra_market_selections.items():
            sharp_extra = market_odds_matrix(odds, profile="sharp", market=extra_market)
            all_extra = market_odds_matrix(odds, market=extra_market)
            has_sharp_extra = set(sharp_extra) == required_selections
            matrix = sharp_extra if has_sharp_extra else all_extra
            baseline_source_by_market[extra_market] = "sharp" if has_sharp_extra else "all_bookmakers"
            extra_complete = set(matrix) == required_selections
            extra_cleansing_succeeded = False
            if matrix:
                try:
                    value_market_probs.update(
                        market.no_vig_probabilities_for_selections(
                            matrix,
                            required_selections,
                        )
                    )
                    extra_cleansing_succeeded = True
                except Exception as exc:
                    print(f"Extra market cleansing faalde voor {fixture.matchup} / {extra_market}: {exc}")

            integrity_metrics.observe_market(
                market=extra_market,
                available=bool(matrix),
                complete=extra_complete,
                cleansing_attempted=extra_complete,
                cleansing_succeeded=(
                    extra_complete
                    and extra_cleansing_succeeded
                ),
                baseline_source=baseline_source_by_market[extra_market],
            )

        comp = competition_by_key.get(fixture.competition_key)
        promoted_teams = comp.promoted_teams if comp else []
        home_is_promoted = _is_promoted(fixture.home_team, promoted_teams)
        away_is_promoted = _is_promoted(fixture.away_team, promoted_teams)
        custom_min_edge = comp.min_edge_threshold if comp and comp.min_edge_threshold is not None else min_edge
        min_edge_by_market = comp.market_min_edge_thresholds if comp else None
        snapshot_id = data_snapshots.create(
            fixture=fixture,
            odds=odds,
            market_probabilities=market_probs,
            standings=standings_by_comp.get(fixture.competition_key),
            lineups=lineups,
            time_window=time_window,
            market_cleansing_failed=market_cleansing_failed,
            extra={
                "odds_fresh": freshness.fresh,
                "odds_freshness_reason": freshness.reason,
                "max_odds_age_minutes": max_odds_age_minutes,
                "sharp_implied_movement": sharp_movement,
                "value_market_probabilities": value_market_probs,
                "baseline_source_by_market": baseline_source_by_market,
                "post_international_break": post_international_break,
                "home_is_promoted": home_is_promoted,
                "away_is_promoted": away_is_promoted,
                "competition_min_edge_threshold": custom_min_edge,
                "competition_market_min_edge_thresholds": min_edge_by_market,
            },
        )

        analysis = ensemble.analyze(
            fixture,
            market_probabilities=market_probs,
            odds=odds,
            standings=standings_by_comp.get(fixture.competition_key),
            competition_type=(comp.type if comp else "league"),
            market_cleansing_failed=market_cleansing_failed,
            time_window=time_window,
            lineup_confirmed=bool(lineups),
            odds_fresh=freshness.fresh,
            data_snapshot_id=snapshot_id,
            sharp_implied_movement=sharp_movement,
            post_international_break=post_international_break,
            home_is_promoted=home_is_promoted,
            away_is_promoted=away_is_promoted,
            promoted_elo=(comp.promoted_elo if comp else None),
        )
        best = best_odds_by_selection(odds, allowed_markets=["1X2", "OVER_UNDER_2_5", "BTTS"])
        model_value_probs = analysis.model_probabilities.as_dict()
        if analysis.poisson:
            model_value_probs.update(analysis.poisson.over_under)
            model_value_probs.update({"BTTS_YES": analysis.poisson.btts.get("YES", 0.0), "BTTS_NO": analysis.poisson.btts.get("NO", 0.0)})
        value = value_engine.best_value_from_maps(
            model_value_probs,
            value_market_probs,
            best,
            custom_min_edge=custom_min_edge,
            min_edge_by_market=min_edge_by_market,
            baseline_source_by_market=baseline_source_by_market,
        )
        pick = selector.select(analysis, value)
        picks.append(pick)
        print(
            f"{fixture.competition_name} | {fixture.matchup} | {pick.status} | "
            f"window={time_window} intl_break={post_international_break} promoted={home_is_promoted}/{away_is_promoted} "
            f"min_edge={custom_min_edge:.1%} lineup={bool(lineups)} odds_fresh={freshness.fresh} "
            f"conf={pick.confidence:.1f} data={pick.data_quality:.1f} unc={pick.uncertainty_score:.1f}"
        )

    if odds_metrics:
        odds_metrics["odds_rows_written"] = sum(len(odds) for _, odds in shadow_observations)
        shadow_db.update_odds_metrics(odds_metrics)

    picks = exposure.apply(picks)
    prediction_log.append(picks)
    shadow_db.record_observations(shadow_observations, picks)
    summary = summarize(picks)
    summary["integrity_diagnostics"] = integrity_metrics.as_dict()
    if odds_metrics:
        summary["odds_discovery"] = odds_metrics
        shadow_db.update_odds_metrics(odds_metrics)
    (out_dir / "daily_summary.txt").write_text(str(summary), encoding="utf-8")
    print("Samenvatting:", summary)

    live_sheet_path = live_sheet.write(picks)
    webhook_ok = live_sheet.push_webhook(picks)
    print(f"Live sheet export opgeslagen: {live_sheet_path} | webhook={'ok' if webhook_ok else 'niet actief'}")

    reporter = TelegramReporter()
    message = reporter.build_daily_message(picks)
    (out_dir / "telegram_message_preview.html").write_text(message, encoding="utf-8")

    if send_daily_report:
        reporter.send(message, disable_notification=True)

    if send_value_alerts:
        for pick in picks:
            notification = notification_state.classify_pick(pick)
            sent = False
            if notification.should_send and notification.action in {"new_value_pick", "upgraded_to_value_pick", "value_pick_changed"}:
                sent = reporter.send(
                    reporter.build_value_pick_alert(pick, notification.action),
                    disable_notification=False,
                )
            elif notification.should_send and notification.action == "value_pick_withdrawn":
                # Premium UX: withdrawals are urgent because members may already have acted on the original alert.
                sent = reporter.send(
                    reporter.build_withdrawal_alert(pick),
                    disable_notification=False,
                )
            notification_state.mark_pick(pick, sent=sent)
            shadow_db.record_notification(pick, action=notification.action, sent=sent)

    if send_heartbeat:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if now.hour >= heartbeat_min_hour_utc and not any(p.status == "VALUE_PICK" for p in picks):
            heartbeat_key = f"{now.date().isoformat()}:{now.hour // 6}"
            if notification_state.should_send_heartbeat(heartbeat_key):
                reporter.send(reporter.build_heartbeat_message(picks), disable_notification=True)
                notification_state.mark_heartbeat(heartbeat_key)

    notification_state.save()
    shadow_db.finish(summary)
    print(f"Output opgeslagen in {out_dir}")


if __name__ == "__main__":
    main()
