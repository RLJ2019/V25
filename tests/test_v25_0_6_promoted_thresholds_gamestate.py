import unittest

from football_agent.models.elo_model import EloModel
from football_agent.models.xg_model import XGModel, TeamFormStats, TeamMatchPerformance
from football_agent.models.value_engine import ValueEngine
from football_agent.models.ensemble import EnsembleModel
from football_agent.schemas import OddsSnapshot, Fixture


class V2506PromotedThresholdsGameStateTests(unittest.TestCase):
    def test_promoted_team_uses_bayesian_lower_elo_prior(self):
        elo = EloModel(default_elo=1500.0, promoted_elo=1435.0)
        self.assertEqual(elo.get("Newly Promoted FC", is_promoted=True), 1435.0)
        self.assertEqual(elo.get("Established FC", is_promoted=False), 1500.0)
        promoted_expectation = elo.expected_home("Promoted", "Established", home_is_promoted=True)
        neutral_expectation = elo.expected_home("Promoted", "Established", home_is_promoted=False)
        self.assertLess(promoted_expectation, neutral_expectation)

    def test_game_state_xg_is_preferred_over_garbage_time_raw_xg(self):
        model = XGModel(half_life_days=30, prefer_game_state_xg=True)
        attack = TeamFormStats(recent_matches=[
            TeamMatchPerformance(
                "2026-01-10T00:00:00Z",
                xg_for=3.0,
                minutes_played=100,
                game_state_xg_for=1.2,
                game_state_minutes=72,
            )
        ])
        opponent = TeamFormStats(recent_matches=[
            TeamMatchPerformance("2026-01-10T00:00:00Z", xg_against=1.0, minutes_played=90)
        ])
        est = model.estimate_team_xg(attack, opponent, fallback=1.25, as_of_utc="2026-01-11T00:00:00Z")
        # 1.2 in 72 state-relevant minutes = 1.5 xG90; raw 3.0/100 would be 2.7 xG90.
        self.assertLess(est, 1.75)
        self.assertGreater(est, 1.20)

    def test_value_engine_uses_competition_specific_market_thresholds(self):
        engine = ValueEngine(min_edge=0.04)
        odds = OddsSnapshot("soft", "BTTS", "BTTS_YES", 2.00, "2026-01-01T00:00:00Z")
        decision = engine.evaluate_selection_from_maps(
            {"BTTS_YES": 0.535},
            {"BTTS_YES": 0.50},
            odds,
            custom_min_edge=0.04,
            min_edge_by_market={"BTTS": 0.08},
        )
        # EV = 7.0%, positive but below the BTTS-specific 8% threshold.
        self.assertEqual(decision.status, "WATCHLIST")
        self.assertIn("8.0%", decision.reason)

    def test_ensemble_promoted_flag_changes_home_probability(self):
        fixture = Fixture("fx", "premier_league", "Premier League", "Promoted FC", "Established FC", "2026-09-14T14:00:00Z")
        model = EnsembleModel()
        market = {"HOME": 0.45, "DRAW": 0.28, "AWAY": 0.27}
        base = model.analyze(fixture, market_probabilities=market, home_is_promoted=False, away_is_promoted=False)
        promoted = model.analyze(fixture, market_probabilities=market, home_is_promoted=True, away_is_promoted=False, promoted_elo=1435.0)
        self.assertLess(promoted.model_probabilities.home, base.model_probabilities.home)


if __name__ == "__main__":
    unittest.main()
