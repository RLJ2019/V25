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


    def test_two_way_btts_no_vig_sums_to_one(self):
        m = MarketModel()
        probs = m.no_vig_probabilities_for_selections(
            {"BTTS_YES": 1.67, "BTTS_NO": 2.15},
            {"BTTS_YES", "BTTS_NO"},
        )

        self.assertEqual(set(probs), {"BTTS_YES", "BTTS_NO"})
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=9)

    def test_two_way_totals_no_vig_sums_to_one(self):
        m = MarketModel()
        probs = m.no_vig_probabilities_for_selections(
            {"OVER_2_5": 1.85, "UNDER_2_5": 1.95},
            {"OVER_2_5", "UNDER_2_5"},
        )

        self.assertEqual(set(probs), {"OVER_2_5", "UNDER_2_5"})
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=9)

    def test_incomplete_two_way_market_raises(self):
        m = MarketModel()

        with self.assertRaises(ValueError):
            m.no_vig_probabilities_for_selections(
                {"BTTS_YES": 1.67},
                {"BTTS_YES", "BTTS_NO"},
            )


if __name__ == "__main__":
    unittest.main()
