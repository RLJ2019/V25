import unittest
from football_agent.models.market_model import MarketModel


class TestMarketModel(unittest.TestCase):
    def test_no_vig_sums_to_one(self):
        m = MarketModel()
        probs = m.no_vig_probabilities({"HOME": 2.0, "DRAW": 3.5, "AWAY": 3.8})
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=9)
        self.assertLess(probs["HOME"], 0.50)

    def test_missing_odds_raise(self):
        m = MarketModel()
        with self.assertRaises(ValueError):
            m.no_vig_probabilities({"HOME": 2.0, "DRAW": 3.5})


if __name__ == "__main__":
    unittest.main()
