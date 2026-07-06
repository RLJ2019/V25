import unittest
from football_agent.decision.pick_selector import PickSelector
from football_agent.schemas import Fixture, MatchAnalysis, ModelProbabilities, FeatureAttribution, ValueDecision


class TestPickSelector(unittest.TestCase):
    def test_blocks_low_data(self):
        f = Fixture('1','eredivisie','Eredivisie','A','B','2026-01-01T12:00:00Z')
        attr = FeatureAttribution(0.5, final_probability=0.6)
        a = MatchAnalysis(f, ModelProbabilities(0.6,0.22,0.18), {'HOME':0.5,'DRAW':0.28,'AWAY':0.22}, attr, attr, attr, None, data_quality=4.0, confidence=8.0, risk_score=2.0, odds=[])
        v = ValueDecision('HOME',0.6,0.5,2.2,0.1,1.67,'VALUE_CANDIDATE','ok','soft')
        p = PickSelector().select(a, v)
        self.assertNotEqual(p.status, 'VALUE_PICK')


if __name__ == "__main__":
    unittest.main()
