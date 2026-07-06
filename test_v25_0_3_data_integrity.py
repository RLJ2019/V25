import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from football_agent.schemas import Fixture, OddsSnapshot, ModelProbabilities, MatchAnalysis, FeatureAttribution, ValueDecision
from football_agent.models.uncertainty_model import UncertaintyModel
from football_agent.storage.data_snapshots import DataSnapshotStore
from football_agent.storage.odds_timeline import OddsTimelineAnalyzer
from football_agent.decision.no_bet_rules import NoBetRules
from football_agent.decision.exposure_manager import ExposureManager
from football_agent.decision.pick_selector import PickSelector
from football_agent.scripts.run_backtest import evaluate_rows


class V2503DataIntegrityTests(unittest.TestCase):
    def fixture(self, fid="fx1", comp="eredivisie"):
        return Fixture(
            id=fid,
            competition_key=comp,
            competition_name="Eredivisie",
            home_team="PSV",
            away_team="Feyenoord",
            kickoff_utc="2026-09-14T14:00:00Z",
        )

    def odds(self):
        return [OddsSnapshot(bookmaker="pinnacle", profile="sharp", market="1X2", selection="HOME", odds=2.10, timestamp_utc="2026-09-14T12:30:00Z")]

    def test_data_snapshot_is_written_and_indexed(self):
        with tempfile.TemporaryDirectory() as d:
            store = DataSnapshotStore(d)
            sid = store.create(
                fixture=self.fixture(),
                odds=self.odds(),
                market_probabilities={"HOME": 0.48, "DRAW": 0.27, "AWAY": 0.25},
                time_window="FINAL",
                lineups=[{"team": "PSV"}],
            )
            self.assertEqual(len(sid), 16)
            self.assertTrue((Path(d) / "data_snapshots" / f"{sid}.json").exists())
            self.assertTrue((Path(d) / "data_snapshots_index.csv").exists())

    def test_odds_freshness(self):
        now = datetime(2026, 9, 14, 13, 0, tzinfo=timezone.utc)
        analyzer = OddsTimelineAnalyzer(max_age_minutes=60)
        fresh = analyzer.freshness(self.odds(), now=now)
        self.assertTrue(fresh.fresh)
        old = analyzer.freshness([
            OddsSnapshot(bookmaker="pinnacle", profile="sharp", market="1X2", selection="HOME", odds=2.10, timestamp_utc="2026-09-14T10:00:00Z")
        ], now=now)
        self.assertFalse(old.fresh)

    def test_uncertainty_interval_widens_for_weak_data(self):
        model = UncertaintyModel()
        strong, strong_u = model.estimate(ModelProbabilities(0.55, 0.25, 0.20), data_quality=9.0, confidence=8.5, time_window="FINAL", lineup_confirmed=True, odds_fresh=True, market_clean=True)
        weak, weak_u = model.estimate(ModelProbabilities(0.55, 0.25, 0.20), data_quality=5.0, confidence=5.0, time_window="EARLY", lineup_confirmed=False, odds_fresh=False, market_clean=False)
        self.assertGreater(weak_u, strong_u)
        self.assertGreater(weak["HOME"][1] - weak["HOME"][0], strong["HOME"][1] - strong["HOME"][0])

    def test_no_bet_blocks_final_without_lineup_and_uncertain_edge(self):
        f = self.fixture()
        attr = FeatureAttribution(market_baseline=0.50, final_probability=0.55)
        analysis = MatchAnalysis(
            fixture=f,
            model_probabilities=ModelProbabilities(0.55, 0.25, 0.20),
            market_probabilities={"HOME": 0.52, "DRAW": 0.28, "AWAY": 0.20},
            attribution_home=attr,
            attribution_draw=attr,
            attribution_away=attr,
            poisson=None,
            data_quality=8.0,
            confidence=8.0,
            risk_score=2.0,
            odds=self.odds(),
            time_window="FINAL",
            lineup_confirmed=False,
            odds_fresh=True,
            probability_intervals={"HOME": (0.49, 0.61)},
            uncertainty_score=4.0,
        )
        value = ValueDecision(selection="HOME", model_probability=0.55, market_probability=0.52, odds=2.1, edge=0.155, fair_odds=1.82, status="VALUE_CANDIDATE", reason="test", bookmaker="pinnacle", probability_edge=0.03, expected_value=0.155)
        reasons = NoBetRules().violations(analysis, value)
        self.assertTrue(any("line" in r.lower() for r in reasons))
        self.assertTrue(any("onzekerheidsmarge" in r.lower() for r in reasons))

    def test_exposure_manager_downgrades_correlated_picks(self):
        f1 = self.fixture("fx1")
        f2 = self.fixture("fx2")
        attr = FeatureAttribution(market_baseline=0.50, final_probability=0.60)
        selector = PickSelector(NoBetRules(max_risk=10, max_uncertainty=10, require_final_lineup=False))
        picks = []
        for f in [f1, f2]:
            analysis = MatchAnalysis(
                fixture=f,
                model_probabilities=ModelProbabilities(0.60, 0.22, 0.18),
                market_probabilities={"HOME": 0.50, "DRAW": 0.28, "AWAY": 0.22},
                attribution_home=attr, attribution_draw=attr, attribution_away=attr,
                poisson=None, data_quality=9, confidence=9, risk_score=1,
                odds=self.odds(), odds_fresh=True, lineup_confirmed=True,
                probability_intervals={"HOME": (0.55, 0.65)}, uncertainty_score=2,
            )
            value = ValueDecision("HOME", 0.60, 0.50, 2.1, 0.26, 1.67, "VALUE_CANDIDATE", "test", "pinnacle", 0.10, 0.26)
            picks.append(selector.select(analysis, value))
        managed = ExposureManager(max_value_picks_per_team=1).apply(picks)
        self.assertEqual(sum(1 for p in managed if p.status == "VALUE_PICK"), 1)
        self.assertEqual(sum(1 for p in managed if p.status == "WATCHLIST"), 1)

    def test_backtest_evaluates_basic_rows(self):
        metrics = evaluate_rows([
            {"competition_key":"epl", "selection":"HOME", "actual":"HOME", "odds":"2.00", "model_probability":"0.58", "closing_odds":"1.85", "status":"VALUE_PICK"},
            {"competition_key":"epl", "selection":"AWAY", "actual":"HOME", "odds":"3.00", "model_probability":"0.40", "closing_odds":"3.20", "status":"VALUE_PICK"},
        ])
        self.assertEqual(metrics["picks"], 2)
        self.assertNotEqual(metrics["avg_brier"], 0)
        self.assertIn("roi", metrics)


if __name__ == "__main__":
    unittest.main()
