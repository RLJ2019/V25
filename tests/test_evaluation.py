import unittest
from football_agent.evaluation.brier import brier_score
from football_agent.evaluation.log_loss import log_loss
from football_agent.evaluation.closing_line_value import clv_decimal


class TestEvaluation(unittest.TestCase):
    def test_brier(self):
        score = brier_score({'HOME':0.6,'DRAW':0.25,'AWAY':0.15}, 'HOME')
        self.assertGreaterEqual(score, 0)
        self.assertLess(score, 1)

    def test_log_loss_positive(self):
        self.assertGreater(log_loss({'HOME':0.6,'DRAW':0.25,'AWAY':0.15}, 'HOME'), 0)
        self.assertAlmostEqual(log_loss({'HOME':0.5,'DRAW':0.25,'AWAY':0.25}, 'HOME'), 0.6931471805599453)

    def test_clv(self):
        self.assertGreater(clv_decimal(2.10, 1.90), 0)


if __name__ == "__main__":
    unittest.main()
