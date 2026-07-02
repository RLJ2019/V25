import unittest
from football_agent.models.ensemble import EnsembleModel
from football_agent.models.xg_model import TeamFormStats
from football_agent.decision.pick_selector import PickSelector
from football_agent.decision.no_bet_rules import NoBetRules
from football_agent.models.value_engine import ValueEngine
from football_agent.schemas import Fixture, OddsSnapshot


class TestEnsembleGuardrails(unittest.TestCase):
    def fixture(self):
        return Fixture(
            id='fx1', competition_key='eredivisie', competition_name='Eredivisie',
            home_team='PSV', away_team='Feyenoord', kickoff_utc='2026-09-14T14:30:00Z'
        )

    def test_xg_attribution_is_not_hardcoded_zero(self):
        model = EnsembleModel()
        analysis = model.analyze(
            self.fixture(),
            market_probabilities={'HOME':0.50,'DRAW':0.25,'AWAY':0.25},
            odds=[OddsSnapshot('sharpbook','1X2','HOME',2.0,'2026-01-01T00:00:00Z')],
            home_form=TeamFormStats(xg_for_last5=2.2, xg_against_last5=0.8),
            away_form=TeamFormStats(xg_for_last5=0.9, xg_against_last5=1.7),
        )
        self.assertNotEqual(analysis.attribution_home.xg_form_adjustment, 0.0)
        self.assertLess(analysis.attribution_away.xg_form_adjustment, 0.0)

    def test_market_fallback_blocks_value_pick_even_with_odds(self):
        fixture = self.fixture()
        odds = [OddsSnapshot('softbook','1X2','HOME',2.20,'2026-01-01T00:00:00Z')]
        analysis = EnsembleModel().analyze(
            fixture,
            market_probabilities=None,
            odds=odds,
            market_cleansing_failed=True,
            home_form=TeamFormStats(xg_for_last5=2.2, xg_against_last5=0.8),
            away_form=TeamFormStats(xg_for_last5=0.9, xg_against_last5=1.7),
        )
        value = ValueEngine(min_edge=0.04).evaluate_selection(analysis.model_probabilities, analysis.market_probabilities, odds[0])
        pick = PickSelector(NoBetRules(require_odds=True, min_data_quality=0, min_confidence=0, max_risk=10)).select(analysis, value)
        self.assertNotEqual(pick.status, 'VALUE_PICK')
        self.assertTrue(any('Market cleansing' in r or 'fallback' in r for r in pick.advice.split(';')))


if __name__ == "__main__":
    unittest.main()
