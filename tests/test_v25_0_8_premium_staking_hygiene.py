import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from football_agent.decision.staking import FractionalKellyStaking
from football_agent.decision.no_bet_rules import NoBetRules
from football_agent.models.value_engine import ValueEngine
from football_agent.schemas import (
    Fixture,
    MatchAnalysis,
    ModelProbabilities,
    FeatureAttribution,
    ValueDecision,
    OddsSnapshot,
    PickDecision,
)
from football_agent.storage.notification_state import NotificationState
from football_agent.reports.live_sheet_export import LiveSheetExporter


class TestV2508PremiumStakingHygiene(unittest.TestCase):
    def test_value_engine_computes_min_acceptable_odds(self):
        engine = ValueEngine(min_edge=0.04)
        odds = OddsSnapshot(bookmaker="Bet365", market="1X2", selection="HOME", odds=1.90, timestamp_utc="2026-01-01T10:00:00Z")
        decision = engine.evaluate_selection_from_maps(
            {"HOME": 0.55, "DRAW": 0.25, "AWAY": 0.20},
            {"HOME": 0.50, "DRAW": 0.27, "AWAY": 0.23},
            odds,
        )
        self.assertAlmostEqual(decision.min_acceptable_odds, 1.04 / 0.55, places=6)
        self.assertEqual(decision.status, "VALUE_CANDIDATE")
        self.assertGreater(decision.expected_value, 0.04)

    def test_staking_is_defensive_and_caps_units(self):
        staking = FractionalKellyStaking(kelly_fraction=0.15, bankroll_units=100, max_units_per_pick=2.0)
        rec = staking.recommend(model_probability=0.62, decimal_odds=2.00, uncertainty_score=2.0, data_quality=9.5, confidence=9.2)
        self.assertGreaterEqual(rec.stake_units, 0.25)
        self.assertLessEqual(rec.stake_units, 2.0)
        weak = staking.recommend(model_probability=0.55, decimal_odds=1.91, uncertainty_score=7.2, data_quality=9.0, confidence=9.0)
        self.assertEqual(weak.stake_units, 0.0)

    def test_no_bet_blocks_tiny_stake_for_candidate(self):
        fixture = Fixture(id="fx1", competition_key="epl", competition_name="Premier League", home_team="A", away_team="B", kickoff_utc="2026-01-01T12:00:00Z")
        analysis = MatchAnalysis(
            fixture=fixture,
            model_probabilities=ModelProbabilities(0.5, 0.25, 0.25),
            market_probabilities={"HOME": 0.45, "DRAW": 0.28, "AWAY": 0.27},
            attribution_home=FeatureAttribution(0.45),
            attribution_draw=FeatureAttribution(0.28),
            attribution_away=FeatureAttribution(0.27),
            poisson=None,
            data_quality=9.0,
            confidence=9.0,
            risk_score=2.0,
            odds=[OddsSnapshot("Bet365", "1X2", "HOME", 2.1, "2026-01-01T10:00:00Z")],
            odds_fresh=True,
            lineup_confirmed=True,
        )
        value = ValueDecision("HOME", 0.5, 0.45, 2.1, 0.05, 2.0, "VALUE_CANDIDATE", "test", min_acceptable_odds=2.08, stake_units=0.0)
        violations = NoBetRules(min_stake_units_for_value=0.25).violations(analysis, value)
        self.assertTrue(any("Stake-indicatie te klein" in v for v in violations))

    def test_notification_state_active_fixture_ids(self):
        with TemporaryDirectory() as td:
            state = NotificationState(Path(td) / "notification_state.json")
            fixture = Fixture(id="fixture-1", competition_key="epl", competition_name="Premier League", home_team="A", away_team="B", kickoff_utc="2026-01-01T12:00:00Z")
            pick = PickDecision(fixture, "WATCHLIST", "Monitoren", "HOME", None, 7.0, 7.0, 2.0, {})
            state.mark_pick(pick)
            self.assertIn("fixture-1", state.active_fixture_ids({"WATCHLIST"}))

    def test_live_sheet_contains_min_odds_and_stake_reason(self):
        with TemporaryDirectory() as td:
            fixture = Fixture(id="fx1", competition_key="epl", competition_name="Premier League", home_team="A", away_team="B", kickoff_utc="2026-01-01T12:00:00Z")
            value = ValueDecision("HOME", 0.55, 0.50, 1.90, 0.045, 1.82, "VALUE_CANDIDATE", "test", min_acceptable_odds=1.89, expected_value=0.045, market="1X2", bookmaker="Bet365")
            pick = PickDecision(fixture, "VALUE_PICK", "A", "HOME", value, 8.0, 8.0, 2.0, {}, stake_units=1.0, stake_reason="test stake")
            exporter = LiveSheetExporter(Path(td) / "live.csv")
            rows = exporter.rows([pick])
            self.assertEqual(rows[0]["min_acceptable_odds"], "1.890")
            self.assertEqual(rows[0]["stake_reason"], "test stake")


if __name__ == "__main__":
    unittest.main()
