import unittest

from football_agent.models.xg_model import XGModel, TeamFormStats, TeamMatchPerformance
from football_agent.models.calendar_context import InternationalBreakFilter
from football_agent.models.uncertainty_model import UncertaintyModel
from football_agent.schemas import ModelProbabilities, Fixture, FeatureAttribution, MatchAnalysis, OddsSnapshot, ValueDecision
from football_agent.decision.no_bet_rules import NoBetRules
from football_agent.decision.staking import FractionalKellyStaking
from football_agent.decision.pick_selector import PickSelector
from football_agent.decision.exposure_manager import ExposureManager
from football_agent.scripts.run_weight_training import train_weights, validate_candidate
from football_agent.scripts.run_backtest import validate_backtest_integrity, evaluate_rows


class V2505RiskXG90RecalibrationTests(unittest.TestCase):
    def test_xg_model_normalizes_to_per90(self):
        model = XGModel(half_life_days=30)
        attack = TeamFormStats(recent_matches=[
            TeamMatchPerformance("2026-01-10T00:00:00Z", xg_for=2.0, goals_for=2.0, minutes_played=100),
        ])
        opponent = TeamFormStats(recent_matches=[
            TeamMatchPerformance("2026-01-10T00:00:00Z", xg_against=1.0, minutes_played=90),
        ])
        est = model.estimate_team_xg(attack, opponent, fallback=1.25, as_of_utc="2026-01-11T00:00:00Z")
        # 2.0 raw xG in 100 minutes becomes 1.8 xG90 before blending.
        self.assertLess(est, 1.55)
        self.assertGreater(est, 1.30)

    def test_international_break_filter_detects_first_round_after_break(self):
        filt = InternationalBreakFilter(windows=[("2026-09-01", "2026-09-09")], days_after=7)
        self.assertTrue(filt.is_post_break_fixture("2026-09-13T14:00:00Z"))
        self.assertFalse(filt.is_post_break_fixture("2026-09-25T14:00:00Z"))

    def test_international_break_widens_uncertainty(self):
        u = UncertaintyModel()
        base, base_score = u.estimate(ModelProbabilities(0.55, 0.25, 0.20), data_quality=8, confidence=8, time_window="PREMATCH", lineup_confirmed=True, odds_fresh=True, market_clean=True)
        brk, brk_score = u.estimate(ModelProbabilities(0.55, 0.25, 0.20), data_quality=8, confidence=8, time_window="PREMATCH", lineup_confirmed=True, odds_fresh=True, market_clean=True, post_international_break=True)
        self.assertGreater(brk_score, base_score)
        self.assertGreater(brk["HOME"][1] - brk["HOME"][0], base["HOME"][1] - base["HOME"][0])

    def test_fractional_kelly_discounts_uncertainty_and_caps_units(self):
        staking = FractionalKellyStaking(kelly_fraction=0.25, bankroll_units=100, max_units_per_pick=1.0)
        rec = staking.recommend(model_probability=0.58, decimal_odds=2.10, uncertainty_score=2, data_quality=9, confidence=9)
        self.assertGreater(rec.raw_kelly_fraction, 0)
        self.assertGreater(rec.stake_units, 0)
        self.assertLessEqual(rec.stake_units, 1.0)
        risky = staking.recommend(model_probability=0.58, decimal_odds=2.10, uncertainty_score=9, data_quality=9, confidence=9)
        self.assertLess(risky.stake_units, rec.stake_units)

    def test_selector_attaches_stake_only_to_value_pick(self):
        f = Fixture("fx", "epl", "Premier League", "A", "B", "2026-09-14T14:00:00Z")
        attr = FeatureAttribution(market_baseline=0.50, final_probability=0.60)
        analysis = MatchAnalysis(
            fixture=f,
            model_probabilities=ModelProbabilities(0.60, 0.22, 0.18),
            market_probabilities={"HOME": 0.50, "DRAW": 0.28, "AWAY": 0.22},
            attribution_home=attr, attribution_draw=attr, attribution_away=attr,
            poisson=None, data_quality=9.0, confidence=9.0, risk_score=1.0,
            odds=[OddsSnapshot("pinnacle", "1X2", "HOME", 2.1, "2026-09-14T12:00:00Z", profile="sharp")],
            odds_fresh=True, lineup_confirmed=True, probability_intervals={"HOME": (0.56, 0.64)}, uncertainty_score=2.0,
        )
        value = ValueDecision("HOME", 0.60, 0.50, 2.1, 0.26, 1.67, "VALUE_CANDIDATE", "test", "pinnacle", 0.10, 0.26)
        pick = PickSelector(NoBetRules(require_final_lineup=False), staking=FractionalKellyStaking(max_units_per_pick=1.0)).select(analysis, value)
        self.assertEqual(pick.status, "VALUE_PICK")
        self.assertGreater(pick.stake_units, 0)

    def test_no_bet_blocks_post_international_break_without_lineup(self):
        f = Fixture("fx", "epl", "Premier League", "A", "B", "2026-09-14T14:00:00Z")
        attr = FeatureAttribution(market_baseline=0.50, final_probability=0.60)
        analysis = MatchAnalysis(
            fixture=f,
            model_probabilities=ModelProbabilities(0.60, 0.22, 0.18),
            market_probabilities={"HOME": 0.50, "DRAW": 0.28, "AWAY": 0.22},
            attribution_home=attr, attribution_draw=attr, attribution_away=attr,
            poisson=None, data_quality=9.0, confidence=7.0, risk_score=1.0,
            odds=[OddsSnapshot("pinnacle", "1X2", "HOME", 2.1, "2026-09-14T12:00:00Z", profile="sharp")],
            odds_fresh=True, lineup_confirmed=False, probability_intervals={"HOME": (0.56, 0.64)}, uncertainty_score=2.0,
            post_international_break=True,
        )
        value = ValueDecision("HOME", 0.60, 0.50, 2.1, 0.26, 1.67, "VALUE_CANDIDATE", "test", "pinnacle", 0.10, 0.26)
        reasons = NoBetRules(require_final_lineup=False).violations(analysis, value)
        self.assertTrue(any("interlandbreak" in r.lower() for r in reasons))

    def test_exposure_manager_caps_total_units(self):
        f1 = Fixture("fx1", "epl", "Premier League", "A", "B", "2026-09-14T14:00:00Z")
        f2 = Fixture("fx2", "eredivisie", "Eredivisie", "C", "D", "2026-09-14T16:00:00Z")
        attr = FeatureAttribution(market_baseline=0.50, final_probability=0.60)
        selector = PickSelector(NoBetRules(require_final_lineup=False, max_uncertainty=10, max_risk=10), staking=FractionalKellyStaking(max_units_per_pick=1.0))
        picks = []
        for f in [f1, f2]:
            analysis = MatchAnalysis(f, ModelProbabilities(0.60, 0.22, 0.18), {"HOME":0.50,"DRAW":0.28,"AWAY":0.22}, attr, attr, attr, None, 9, 9, 1, odds=[OddsSnapshot("p","1X2","HOME",2.1,"2026-09-14T12:00:00Z")], odds_fresh=True, lineup_confirmed=True, probability_intervals={"HOME":(0.56,0.64)}, uncertainty_score=2)
            value = ValueDecision("HOME", 0.60, 0.50, 2.1, 0.26, 1.67, "VALUE_CANDIDATE", "test", "p", 0.10, 0.26)
            picks.append(selector.select(analysis, value))
        managed = ExposureManager(max_total_units_per_day=1.0, max_value_picks_per_team=10, max_value_picks_per_competition=10).apply(picks)
        self.assertEqual(sum(1 for p in managed if p.status == "VALUE_PICK"), 1)

    def test_weight_training_candidate_validation_requires_sample_and_can_validate(self):
        rows = []
        for i in range(120):
            rows.append({
                "status":"VALUE_PICK", "competition_key":"epl", "selection":"HOME", "actual":"HOME" if i < 70 else "AWAY",
                "model_probability":"0.55", "selected_attr_elo":"0.03" if i < 70 else "-0.01", "selected_attr_xg":"0.02" if i < 70 else "0.00",
            })
        candidate = train_weights(rows, min_rows=100)
        validation = validate_candidate(rows, candidate, min_rows=100)
        self.assertIn("epl", candidate["competitions"])
        self.assertEqual(validation["usable_rows"], 120)
        self.assertIn("promotion_recommended", validation)

    def test_backtest_integrity_excludes_lookahead_rows(self):
        rows = [
            {"competition_key":"epl", "selection":"HOME", "actual":"HOME", "odds":"2.0", "model_probability":"0.58", "kickoff_utc":"2026-09-14T14:00:00Z", "prediction_time_utc":"2026-09-14T13:00:00Z"},
            {"competition_key":"epl", "selection":"HOME", "actual":"HOME", "odds":"2.0", "model_probability":"0.58", "kickoff_utc":"2026-09-14T14:00:00Z", "prediction_time_utc":"2026-09-14T15:00:00Z"},
        ]
        valid, warnings = validate_backtest_integrity(rows)
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(warnings), 1)
        metrics = evaluate_rows(valid)
        self.assertEqual(metrics["picks"], 1)


if __name__ == "__main__":
    unittest.main()
