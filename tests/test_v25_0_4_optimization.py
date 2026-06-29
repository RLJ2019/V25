import tempfile
import unittest
from pathlib import Path

from football_agent.models.xg_model import XGModel, TeamFormStats, TeamMatchPerformance
from football_agent.storage.odds_timeline import OddsTimelineAnalyzer
from football_agent.schemas import OddsSnapshot, ModelProbabilities, Fixture, MatchAnalysis, FeatureAttribution, ValueDecision
from football_agent.models.value_engine import ValueEngine
from football_agent.models.uncertainty_model import UncertaintyModel
from football_agent.decision.no_bet_rules import NoBetRules
from football_agent.scripts.run_weight_training import train_weights


class V2504OptimizationTests(unittest.TestCase):
    def test_time_decay_weights_recent_xg_more_heavily(self):
        model = XGModel(half_life_days=7)
        attack = TeamFormStats(recent_matches=[
            TeamMatchPerformance("2026-01-01T00:00:00Z", xg_for=0.4, goals_for=0.0),
            TeamMatchPerformance("2026-01-28T00:00:00Z", xg_for=2.4, goals_for=3.0),
        ])
        opponent = TeamFormStats(recent_matches=[
            TeamMatchPerformance("2026-01-28T00:00:00Z", xg_against=1.6),
        ])
        xg = model.estimate_team_xg(attack, opponent, as_of_utc="2026-01-29T00:00:00Z")
        self.assertGreater(xg, 1.5)

    def test_sharp_implied_movement_detects_shortening_and_drift(self):
        analyzer = OddsTimelineAnalyzer()
        movement = analyzer.sharp_implied_movement([
            OddsSnapshot("pinnacle", "1X2", "HOME", 1.80, "2026-09-14T12:00:00Z", profile="sharp", opening_odds=2.00),
            OddsSnapshot("pinnacle", "1X2", "AWAY", 4.50, "2026-09-14T12:00:00Z", profile="sharp", opening_odds=4.00),
        ])
        self.assertGreater(movement["HOME"], 0)
        self.assertLess(movement["AWAY"], 0)

    def test_value_engine_can_select_over_under_market(self):
        value = ValueEngine(min_edge=0.04).best_value_from_maps(
            {"HOME": 0.50, "DRAW": 0.25, "AWAY": 0.25, "OVER_2_5": 0.60, "UNDER_2_5": 0.40},
            {"HOME": 0.50, "DRAW": 0.25, "AWAY": 0.25, "OVER_2_5": 0.52, "UNDER_2_5": 0.48},
            {"OVER_2_5": OddsSnapshot("softbook", "OVER_UNDER_2_5", "OVER_2_5", 2.05, "2026-09-14T12:00:00Z", profile="soft")},
        )
        self.assertEqual(value.market, "OVER_UNDER_2_5")
        self.assertEqual(value.selection, "OVER_2_5")
        self.assertEqual(value.status, "VALUE_CANDIDATE")

    def test_uncertainty_bootstrap_returns_intervals(self):
        u = UncertaintyModel()
        intervals, score = u.estimate(
            ModelProbabilities(0.55, 0.25, 0.20),
            data_quality=8.5,
            confidence=8.0,
            time_window="PREMATCH",
            lineup_confirmed=True,
            odds_fresh=True,
            market_clean=True,
            attribution_matrix={
                "HOME": {"market_baseline": 0.50, "elo_adjustment": 0.03, "xg_form_adjustment": 0.02, "final_probability": 0.55},
                "DRAW": {"market_baseline": 0.27, "elo_adjustment": -0.01, "final_probability": 0.25},
                "AWAY": {"market_baseline": 0.23, "elo_adjustment": -0.02, "final_probability": 0.20},
            },
            iterations=150,
        )
        self.assertIn("HOME", intervals)
        self.assertGreater(intervals["HOME"][1], intervals["HOME"][0])
        self.assertGreaterEqual(score, 0)

    def test_no_bet_blocks_adverse_sharp_movement(self):
        f = Fixture("fx", "epl", "Premier League", "A", "B", "2026-09-14T14:00:00Z")
        attr = FeatureAttribution(market_baseline=0.50, final_probability=0.58)
        analysis = MatchAnalysis(
            fixture=f,
            model_probabilities=ModelProbabilities(0.58, 0.22, 0.20),
            market_probabilities={"HOME": 0.50, "DRAW": 0.28, "AWAY": 0.22},
            attribution_home=attr, attribution_draw=attr, attribution_away=attr,
            poisson=None, data_quality=9.0, confidence=9.0, risk_score=1.0,
            odds=[OddsSnapshot("pinnacle", "1X2", "HOME", 2.0, "2026-09-14T12:00:00Z", profile="sharp")],
            odds_fresh=True, lineup_confirmed=True, probability_intervals={"HOME": (0.55, 0.62)},
            uncertainty_score=2.0, sharp_implied_movement={"HOME": -0.04},
        )
        value = ValueDecision("HOME", 0.58, 0.50, 2.0, 0.16, 1.72, "VALUE_CANDIDATE", "test", "pinnacle", 0.08, 0.16)
        reasons = NoBetRules(require_final_lineup=False).violations(analysis, value)
        self.assertTrue(any("Sharp markt" in r for r in reasons))

    def test_weight_training_writes_conservative_payload(self):
        rows = []
        for i in range(120):
            rows.append({
                "status": "VALUE_PICK", "competition_key": "eredivisie", "selection": "HOME", "actual": "HOME" if i < 70 else "AWAY",
                "selected_attr_elo": "0.03" if i < 70 else "-0.01",
                "selected_attr_xg": "0.02" if i < 70 else "0.00",
            })
        payload = train_weights(rows, min_rows=100)
        self.assertIn("eredivisie", payload["competitions"])
        self.assertIn("elo_adjustment", payload["competitions"]["eredivisie"])


if __name__ == "__main__":
    unittest.main()
