import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from football_agent.decision.staking import FractionalKellyStaking
from football_agent.models.ensemble import EnsembleModel
from football_agent.models.value_engine import ValueEngine
from football_agent.models.calibration import CalibrationModel, IsotonicSegment
from football_agent.models.market_attributors import MarketAttributionFactory
from football_agent.reports.gemini_explainer import GeminiExplainer
from football_agent.reports.live_sheet_export import LiveSheetExporter
from football_agent.schemas import Fixture, OddsSnapshot, PickDecision, ValueDecision, MatchAnalysis, ModelProbabilities, FeatureAttribution
from football_agent.storage.notification_state import NotificationState


class TestV2509PremiumReliability(unittest.TestCase):
    def fixture(self):
        return Fixture('fx1','eredivisie','Eredivisie','PSV','Feyenoord','2099-09-14T14:00:00Z')

    def test_withdrawal_is_loud_and_state_save_is_atomic(self):
        with TemporaryDirectory() as d:
            state = NotificationState(Path(d) / 'notification_state.json')
            value = ValueDecision('HOME',0.58,0.50,2.0,0.16,1.72,'VALUE_CANDIDATE','ok')
            pick = PickDecision(self.fixture(),'VALUE_PICK','Thuisteam wint','HOME',value,8,8,2,{})
            state.mark_pick(pick, sent=True)
            withdrawn = PickDecision(self.fixture(),'WATCHLIST','Monitoren','HOME',value,8,8,2,{})
            decision = state.classify_pick(withdrawn)
            self.assertTrue(decision.should_send)
            self.assertFalse(decision.disable_notification)
            state.save()
            self.assertTrue((Path(d) / 'notification_state.json').exists())
            self.assertFalse((Path(d) / 'notification_state.json.tmp').exists())

    def test_staking_uses_single_risk_multiplier_not_triple_discount(self):
        staking = FractionalKellyStaking(kelly_fraction=0.15, bankroll_units=100, max_units_per_pick=2.0)
        rec = staking.recommend(model_probability=0.62, decimal_odds=2.00, uncertainty_score=2.0, data_quality=9.5, confidence=9.2)
        self.assertGreaterEqual(rec.stake_units, 1.0)
        self.assertLessEqual(rec.stake_units, 2.0)
        self.assertIn('één risk multiplier', rec.reason)

    def test_value_engine_carries_sharp_baseline_transparency(self):
        odds = OddsSnapshot('Bet365','1X2','HOME',1.95,'2026-01-01T10:00:00Z',profile='soft')
        v = ValueEngine(min_edge=0.04).evaluate_selection_from_maps(
            {'HOME':0.58,'DRAW':0.22,'AWAY':0.20},
            {'HOME':0.50,'DRAW':0.27,'AWAY':0.23},
            odds,
            baseline_source_by_market={'1X2':'sharp'},
        )
        self.assertEqual(v.baseline_source, 'sharp')
        self.assertAlmostEqual(v.sharp_fair_odds, 2.0)
        self.assertEqual(v.selected_odds_profile, 'soft')

    def test_logit_attribution_is_order_invariant(self):
        model = EnsembleModel()
        contributions = [('a',0.03),('b',-0.01),('c',0.02)]
        eff1, final1 = model._apply_logit_attribution(0.55, contributions)
        eff2, final2 = model._apply_logit_attribution(0.55, list(reversed(contributions)))
        self.assertAlmostEqual(final1, final2, places=12)
        self.assertAlmostEqual(sum(eff1.values()), final1 - 0.55, places=12)
        self.assertAlmostEqual(sum(eff2.values()), final2 - 0.55, places=12)

    def test_gemini_prompt_blocks_jargon(self):
        prompt = GeminiExplainer(api_key=None)._prompt({'value': {'selection':'HOME'}})
        self.assertIn('Gebruik GEEN technische/statistische termen', prompt)
        self.assertIn('Poisson', prompt)
        self.assertIn('overround', prompt)

    def test_market_attributor_handles_over_under(self):
        f = self.fixture()
        attr = FeatureAttribution(0.5, final_probability=0.5)
        from football_agent.schemas import PoissonProjection
        analysis = MatchAnalysis(
            f,
            ModelProbabilities(0.5,0.25,0.25),
            {'HOME':0.5,'DRAW':0.25,'AWAY':0.25},
            attr,attr,attr,
            PoissonProjection(1.8,1.3,'2-1',0.1,{'HOME':0.5,'DRAW':0.25,'AWAY':0.25},{'OVER_2_5':0.58,'UNDER_2_5':0.42},{'YES':0.62,'NO':0.38}),
            8,8,2,
        )
        value = ValueDecision('OVER_2_5',0.58,0.52,1.9,0.102,1.72,'VALUE_CANDIDATE','ok',market='OVER_UNDER_2_5')
        info = MarketAttributionFactory().attribute(analysis,value)
        self.assertEqual(info['market'], 'OVER_UNDER_2_5')
        self.assertIn('Goals-markt', info['summary'])

    def test_live_sheet_webhook_retries_with_idempotency_key(self):
        f = self.fixture()
        v = ValueDecision('HOME',0.58,0.50,2.0,0.16,1.72,'VALUE_CANDIDATE','ok',sharp_fair_odds=2.0,baseline_source='sharp')
        p = PickDecision(f,'VALUE_PICK','Thuisteam wint','HOME',v,8,8,2,{})
        with TemporaryDirectory() as d, patch.dict('os.environ', {'GOOGLE_SHEET_WEBHOOK_URL':'https://example.com/hook','LIVE_SHEET_WEBHOOK_RETRIES':'2'}), patch('football_agent.reports.live_sheet_export.requests.post') as post:
            post.return_value.raise_for_status.return_value = None
            ok = LiveSheetExporter(Path(d)/'live.csv').push_webhook([p])
            self.assertTrue(ok)
            payload = post.call_args.kwargs['json']
            self.assertIn('idempotency_key', payload)
            self.assertIn('Idempotency-Key', post.call_args.kwargs['headers'])

    def test_calibration_tail_is_smooth_not_nearest_step(self):
        m = CalibrationModel()
        m.isotonic_segments['x'] = [
            IsotonicSegment(0.2,0.3,0.25,20),
            IsotonicSegment(0.4,0.5,0.45,20),
        ]
        low = m.calibrate_probability('x',0.1)
        near = m.calibrate_probability('x',0.19)
        self.assertNotEqual(low, 0.25)
        self.assertLessEqual(low, near)


if __name__ == '__main__':
    unittest.main()
