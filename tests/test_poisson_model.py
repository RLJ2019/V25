import unittest
from football_agent.models.poisson_model import PoissonModel


class TestPoissonModel(unittest.TestCase):
    def test_probabilities_sum(self):
        p = PoissonModel().project(1.4, 1.0)
        self.assertAlmostEqual(sum(p.outcome_probabilities.values()), 1.0, places=6)
        self.assertIn('-', p.most_likely_score)
        self.assertGreaterEqual(p.over_under['OVER_2_5'], 0)
        self.assertLessEqual(p.over_under['OVER_2_5'], 1)


if __name__ == "__main__":
    unittest.main()
