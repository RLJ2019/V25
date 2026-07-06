import unittest
from football_agent.models.poisson_model import PoissonModel
from football_agent.models.ensemble import EnsembleModel
from football_agent.models.motivation_model import MotivationModel, StandingRow
from football_agent.models.injury_model import InjuryModel, PlayerAbsence
from football_agent.models.calibration import CalibrationModel, CalibrationPoint
from football_agent.schemas import Fixture, OddsSnapshot


class TestV2502ProfessionalMath(unittest.TestCase):
    def test_dixon_coles_increases_low_score_draws_with_negative_rho(self):
        independent = PoissonModel(dixon_coles_rho=0.0).project(1.15, 1.05, use_dixon_coles=False)
        dc = PoissonModel(dixon_coles_rho=-0.08).project(1.15, 1.05, use_dixon_coles=True)
        self.assertAlmostEqual(sum(dc.outcome_probabilities.values()), 1.0, places=6)
        self.assertGreater(dc.outcome_probabilities['DRAW'], independent.outcome_probabilities['DRAW'])

    def test_logit_overlay_keeps_extreme_baselines_stable(self):
        fixture = Fixture('1','premier_league','Premier League','Manchester City','Burnley','2026-01-01T12:00:00Z')
        analysis = EnsembleModel().analyze(
            fixture,
            market_probabilities={'HOME':0.85,'DRAW':0.10,'AWAY':0.05},
            odds=[OddsSnapshot('sharpbook','1X2','HOME',1.18,'2026-01-01T00:00:00Z')],
        )
        self.assertLess(analysis.model_probabilities.home, 0.97)
        self.assertAlmostEqual(sum(analysis.model_probabilities.as_dict().values()), 1.0, places=6)

    def test_motivation_from_standings_is_objective_and_capped(self):
        table = [
            StandingRow('Ajax',1,72,30,40),
            StandingRow('PSV',2,70,30,38),
            StandingRow('Team C',10,38,30,0),
            StandingRow('Team D',15,27,30,-10),
            StandingRow('Team E',16,26,30,-12),
            StandingRow('Team F',17,24,30,-20),
            StandingRow('Team G',18,20,30,-30),
        ]
        model = MotivationModel()
        self.assertGreater(model.from_standings('PSV', table), 0)
        self.assertLessEqual(abs(model.from_standings('Team E', table)), 0.025)

    def test_dynamic_replacement_quality_uses_market_value_ratio(self):
        model = InjuryModel(max_total_impact=0.12)
        static = model.team_impact([PlayerAbsence('Starter','A','CB',role='starter',replacement_quality=0.75)])
        thin_squad = model.team_impact([PlayerAbsence('Starter','A','CB',role='starter',replacement_quality=0.75,player_market_value=20_000_000,replacement_market_value=2_000_000)])
        deep_squad = model.team_impact([PlayerAbsence('Starter','A','CB',role='starter',replacement_quality=0.75,player_market_value=20_000_000,replacement_market_value=22_000_000)])
        self.assertGreater(thin_squad, static)
        self.assertLess(deep_squad, static)

    def test_isotonic_calibration_monotonic_segments(self):
        model = CalibrationModel(min_samples=5)
        points = [
            CalibrationPoint('eredivisie',0.20,0),
            CalibrationPoint('eredivisie',0.30,0),
            CalibrationPoint('eredivisie',0.40,1),
            CalibrationPoint('eredivisie',0.60,1),
            CalibrationPoint('eredivisie',0.80,1),
        ]
        model.fit_isotonic(points, min_samples=5)
        self.assertTrue(model.isotonic_segments['eredivisie'])
        low = model.calibrate_probability('eredivisie',0.25)
        high = model.calibrate_probability('eredivisie',0.75)
        self.assertLessEqual(low, high)


if __name__ == '__main__':
    unittest.main()
