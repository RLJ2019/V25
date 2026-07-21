from __future__ import annotations

import unittest
from types import SimpleNamespace

from football_agent.decision.exposure_manager import ExposureManager
from football_agent.decision.pick_selector import PickSelector
from football_agent.reports.daily_summary import summarize
from football_agent.schemas import (
    FeatureAttribution,
    Fixture,
    MatchAnalysis,
    ModelProbabilities,
    ValueDecision,
)


class _NoViolations:
    def violations(self, analysis, value):
        return []


class _FixedStaking:
    def recommend(self, **kwargs):
        return SimpleNamespace(
            raw_kelly_fraction=0.08,
            fractional_kelly=0.02,
            stake_units=0.50,
            reason="V25.1.4 characterization stake",
        )


class _FixedMarketAttributor:
    def attribute(self, analysis, value):
        return {"source": "V25.1.4-characterization"}


def _analysis(
    fixture_id: str,
    *,
    home_team: str,
    away_team: str,
) -> MatchAnalysis:
    fixture = Fixture(
        id=fixture_id,
        competition_key="eredivisie",
        competition_name="Eredivisie",
        home_team=home_team,
        away_team=away_team,
        kickoff_utc="2026-09-14T14:00:00Z",
    )
    attribution = FeatureAttribution(
        market_baseline=0.50,
        final_probability=0.60,
    )
    return MatchAnalysis(
        fixture=fixture,
        model_probabilities=ModelProbabilities(
            home=0.60,
            draw=0.22,
            away=0.18,
        ),
        market_probabilities={
            "HOME": 0.50,
            "DRAW": 0.28,
            "AWAY": 0.22,
        },
        attribution_home=attribution,
        attribution_draw=attribution,
        attribution_away=attribution,
        poisson=None,
        data_quality=9.0,
        confidence=9.0,
        risk_score=1.0,
        notes=["V25.1.4 characterization"],
        odds=[],
        market_cleansing_failed=False,
        market_probabilities_are_fallback=False,
        probability_intervals={"HOME": (0.55, 0.65)},
        uncertainty_score=2.0,
        data_snapshot_id="snapshot-characterization",
        time_window="FINAL",
        lineup_confirmed=True,
        odds_fresh=True,
    )


def _value(expected_value: float) -> ValueDecision:
    return ValueDecision(
        selection="HOME",
        model_probability=0.60,
        market_probability=0.50,
        odds=2.10,
        edge=expected_value,
        fair_odds=1.67,
        status="VALUE_CANDIDATE",
        reason="V25.1.4 characterization",
        bookmaker="pinnacle",
        probability_edge=0.10,
        expected_value=expected_value,
        market="1X2",
        baseline_source="sharp",
        sharp_market_probability=0.50,
        sharp_fair_odds=2.00,
        selected_odds_profile="sharp",
    )


def _fingerprint(pick):
    value = pick.value_decision
    return {
        "fixture_id": pick.fixture.id,
        "status": pick.status,
        "selection": pick.selection,
        "market": value.market if value else None,
        "bookmaker": value.bookmaker if value else None,
        "odds": value.odds if value else None,
        "model_probability": value.model_probability if value else None,
        "market_probability": value.market_probability if value else None,
        "edge": value.edge if value else None,
        "confidence": pick.confidence,
        "data_quality": pick.data_quality,
        "raw_kelly_fraction": pick.raw_kelly_fraction,
        "fractional_kelly": pick.fractional_kelly,
        "stake_units": pick.stake_units,
    }


class V2515IntegrityDiagnosticsCharacterizationTests(unittest.TestCase):
    def test_v2514_pick_and_stake_fingerprint_after_exposure(self):
        selector = PickSelector(
            no_bet_rules=_NoViolations(),
            staking=_FixedStaking(),
        )
        selector.market_attributor = _FixedMarketAttributor()

        first = selector.select(
            _analysis(
                "fx-characterization-1",
                home_team="PSV",
                away_team="Feyenoord",
            ),
            _value(0.26),
        )
        second = selector.select(
            _analysis(
                "fx-characterization-2",
                home_team="PSV",
                away_team="Ajax",
            ),
            _value(0.20),
        )

        managed = ExposureManager(
            max_value_picks_per_competition=3,
            max_value_picks_per_team=1,
            max_value_picks_per_fixture=1,
            max_total_units_per_day=3.0,
        ).apply([first, second])

        self.assertEqual(
            [_fingerprint(pick) for pick in managed],
            [
                {
                    "fixture_id": "fx-characterization-1",
                    "status": "VALUE_PICK",
                    "selection": "HOME",
                    "market": "1X2",
                    "bookmaker": "pinnacle",
                    "odds": 2.10,
                    "model_probability": 0.60,
                    "market_probability": 0.50,
                    "edge": 0.26,
                    "confidence": 9.0,
                    "data_quality": 9.0,
                    "raw_kelly_fraction": 0.08,
                    "fractional_kelly": 0.02,
                    "stake_units": 0.50,
                },
                {
                    "fixture_id": "fx-characterization-2",
                    "status": "WATCHLIST",
                    "selection": "HOME",
                    "market": "1X2",
                    "bookmaker": "pinnacle",
                    "odds": 2.10,
                    "model_probability": 0.60,
                    "market_probability": 0.50,
                    "edge": 0.20,
                    "confidence": 9.0,
                    "data_quality": 9.0,
                    "raw_kelly_fraction": 0.08,
                    "fractional_kelly": 0.0,
                    "stake_units": 0.0,
                },
            ],
        )

    def test_existing_daily_summary_contract_is_unchanged(self):
        selector = PickSelector(
            no_bet_rules=_NoViolations(),
            staking=_FixedStaking(),
        )
        selector.market_attributor = _FixedMarketAttributor()

        pick = selector.select(
            _analysis(
                "fx-summary-characterization",
                home_team="AZ",
                away_team="Twente",
            ),
            _value(0.26),
        )

        summary = summarize([pick])

        self.assertEqual(
            summary,
            {
                "scanned": 1,
                "value_picks": 1,
                "watchlist": 0,
                "no_bet": 0,
            },
        )
        self.assertEqual(
            set(summary),
            {"scanned", "value_picks", "watchlist", "no_bet"},
        )


if __name__ == "__main__":
    unittest.main()
