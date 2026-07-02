import unittest
from football_agent.models.injury_model import InjuryModel, PlayerAbsence


class TestInjuryModel(unittest.TestCase):
    def test_synergy_capped(self):
        model = InjuryModel(max_total_impact=0.12)
        absences = [
            PlayerAbsence('LB', 'Team', 'LB', role='starter', side='left', replacement_quality=0.5),
            PlayerAbsence('LW', 'Team', 'LW', role='key', side='left', replacement_quality=0.5),
            PlayerAbsence('ST', 'Team', 'ST', role='key', replacement_quality=0.3),
        ]
        impact = model.team_impact(absences)
        self.assertGreater(impact, 0)
        self.assertLessEqual(impact, 0.12)


if __name__ == "__main__":
    unittest.main()
