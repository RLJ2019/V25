import unittest
from football_agent.models.value_engine import ValueEngine
from football_agent.schemas import ModelProbabilities, OddsSnapshot


class TestValueEngine(unittest.TestCase):
    def test_value_candidate_uses_financial_ev(self):
        ev = ValueEngine(min_edge=0.04)
        odds = OddsSnapshot('softbook', '1X2', 'HOME', 2.20, '2026-01-01T00:00:00Z')
        d = ev.evaluate_selection(ModelProbabilities(0.58, 0.24, 0.18), {'HOME':0.50,'DRAW':0.28,'AWAY':0.22}, odds)
        self.assertEqual(d.status, 'VALUE_CANDIDATE')
        self.assertAlmostEqual(d.probability_edge, 0.08)
        self.assertAlmostEqual(d.expected_value, (0.58 * 2.20) - 1.0)
        self.assertAlmostEqual(d.edge, d.expected_value)

    def test_best_value_sorts_by_ev_not_raw_probability_edge(self):
        ev = ValueEngine(min_edge=0.04)
        best = ev.best_value(
            ModelProbabilities(0.88, 0.06, 0.28),
            {'HOME':0.80,'DRAW':0.06,'AWAY':0.20},
            {
                'HOME': OddsSnapshot('softbook', '1X2', 'HOME', 1.25, '2026-01-01T00:00:00Z'),
                'AWAY': OddsSnapshot('softbook', '1X2', 'AWAY', 5.00, '2026-01-01T00:00:00Z'),
            }
        )
        self.assertEqual(best.selection, 'AWAY')
        self.assertAlmostEqual(best.probability_edge, 0.08)
        self.assertAlmostEqual(best.expected_value, 0.40)

    def test_no_odds_no_bet(self):
        d = ValueEngine().evaluate_selection(ModelProbabilities(0.58,0.24,0.18), {'HOME':0.50,'DRAW':0.28,'AWAY':0.22}, None)
        self.assertEqual(d.status, 'NO_BET')


if __name__ == "__main__":
    unittest.main()
