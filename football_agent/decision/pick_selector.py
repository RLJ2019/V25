from __future__ import annotations

from typing import Dict
from football_agent.schemas import MatchAnalysis, PickDecision, ValueDecision
from football_agent.storage.model_versions import MODEL_VERSION, CONFIG_VERSION, FEATURE_SET_VERSION, CALIBRATION_VERSION
from .no_bet_rules import NoBetRules
from .staking import FractionalKellyStaking
from football_agent.models.market_attributors import MarketAttributionFactory


class PickSelector:
    def __init__(self, no_bet_rules: NoBetRules | None = None, staking: FractionalKellyStaking | None = None):
        self.no_bet_rules = no_bet_rules or NoBetRules()
        self.staking = staking or FractionalKellyStaking()
        self.market_attributor = MarketAttributionFactory()

    def select(self, analysis: MatchAnalysis, value: ValueDecision) -> PickDecision:
        stake = self.staking.recommend(
            model_probability=value.model_probability,
            decimal_odds=value.odds,
            uncertainty_score=analysis.uncertainty_score,
            data_quality=analysis.data_quality,
            confidence=analysis.confidence,
        )
        value.raw_kelly_fraction = stake.raw_kelly_fraction
        value.fractional_kelly = stake.fractional_kelly
        value.stake_units = stake.stake_units
        value.stake_reason = stake.reason
        violations = self.no_bet_rules.violations(analysis, value)
        critical_market_violation = any(
            "Market cleansing" in reason or "fallback" in reason or "marktbaseline" in reason
            for reason in violations
        )
        final_lineup_violation = any("line-up" in reason.lower() for reason in violations)
        if not violations and value.status == "VALUE_CANDIDATE":
            status = "VALUE_PICK"
            advice = self._advice_from_selection(value.selection)
        elif not critical_market_violation and not final_lineup_violation and (value.status == "WATCHLIST" or (value.expected_value >= 0.02 and len(violations) <= 2)):
            status = "WATCHLIST"
            advice = f"Monitoren: {value.reason}"
        else:
            status = "NO_BET"
            advice = "Geen pick: " + "; ".join(violations[:5])
        facts: Dict = {
            "market_probabilities": analysis.market_probabilities,
            "model_probabilities": analysis.model_probabilities.as_dict(),
            "probability_intervals": analysis.probability_intervals,
            "uncertainty_score": analysis.uncertainty_score,
            "data_snapshot_id": analysis.data_snapshot_id,
            "time_window": analysis.time_window,
            "lineup_confirmed": analysis.lineup_confirmed,
            "odds_fresh": analysis.odds_fresh,
            "attribution": {
                "HOME": analysis.attribution_home.as_dict(),
                "DRAW": analysis.attribution_draw.as_dict(),
                "AWAY": analysis.attribution_away.as_dict(),
            },
            "poisson": analysis.poisson.__dict__ if analysis.poisson else None,
            "value": value.__dict__,
            "market_attribution": self.market_attributor.attribute(analysis, value),
            "sharp_implied_movement": analysis.sharp_implied_movement,
            "post_international_break": analysis.post_international_break,
            "stake": {
                "raw_kelly_fraction": value.raw_kelly_fraction,
                "fractional_kelly": value.fractional_kelly,
                "stake_units": value.stake_units,
                "stake_reason": value.stake_reason,
            },
            "notes": analysis.notes,
            "violations": violations,
            "market_cleansing_failed": analysis.market_cleansing_failed,
            "market_probabilities_are_fallback": analysis.market_probabilities_are_fallback,
            "model_version": MODEL_VERSION,
            "config_version": CONFIG_VERSION,
            "feature_set_version": FEATURE_SET_VERSION,
            "calibration_version": CALIBRATION_VERSION,
        }
        low = high = None
        if value.selection and value.selection in analysis.probability_intervals:
            low, high = analysis.probability_intervals[value.selection]
        return PickDecision(
            fixture=analysis.fixture,
            status=status,
            advice=advice,
            selection=value.selection if value.selection != "NONE" else None,
            value_decision=value,
            confidence=analysis.confidence,
            data_quality=analysis.data_quality,
            risk_score=analysis.risk_score,
            explanation_facts=facts,
            model_version=MODEL_VERSION,
            config_version=CONFIG_VERSION,
            feature_set_version=FEATURE_SET_VERSION,
            calibration_version=CALIBRATION_VERSION,
            data_snapshot_id=analysis.data_snapshot_id,
            time_window=analysis.time_window,
            lineup_confirmed=analysis.lineup_confirmed,
            uncertainty_score=analysis.uncertainty_score,
            probability_interval_low=low,
            probability_interval_high=high,
            post_international_break=analysis.post_international_break,
            raw_kelly_fraction=value.raw_kelly_fraction if status == "VALUE_PICK" else 0.0,
            fractional_kelly=value.fractional_kelly if status == "VALUE_PICK" else 0.0,
            stake_units=value.stake_units if status == "VALUE_PICK" else 0.0,
            stake_reason=value.stake_reason,
        )

    def _advice_from_selection(self, selection: str) -> str:
        return {
            "HOME": "Thuisteam wint",
            "DRAW": "Gelijkspel",
            "AWAY": "Uitteam wint",
            "OVER_2_5": "Over 2.5 goals",
            "UNDER_2_5": "Under 2.5 goals",
            "BTTS_YES": "Beide teams scoren: ja",
            "BTTS_NO": "Beide teams scoren: nee",
        }.get(selection, selection)
