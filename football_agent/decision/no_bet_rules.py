from __future__ import annotations

from typing import List
from football_agent.schemas import MatchAnalysis, ValueDecision


class NoBetRules:
    def __init__(
        self,
        require_odds: bool = True,
        min_data_quality: float = 7.0,
        min_confidence: float = 7.0,
        max_risk: float = 4.5,
        max_uncertainty: float = 6.5,
        require_final_lineup: bool = True,
        min_stake_units_for_value: float = 0.25,
    ):
        self.require_odds = require_odds
        self.min_data_quality = min_data_quality
        self.min_confidence = min_confidence
        self.max_risk = max_risk
        self.max_uncertainty = max_uncertainty
        self.require_final_lineup = require_final_lineup
        self.min_stake_units_for_value = max(0.0, min_stake_units_for_value)

    def violations(self, analysis: MatchAnalysis, value: ValueDecision) -> List[str]:
        reasons: List[str] = []
        if analysis.market_cleansing_failed:
            reasons.append("Market cleansing is gefaald; fantoom-edge wordt geblokkeerd.")
        if analysis.market_probabilities_are_fallback:
            reasons.append("Geen echte gecleande marktbaseline; fallback-markt mag geen value pick opleveren.")
        if self.require_odds and not analysis.odds:
            reasons.append("Geen verse odds beschikbaar.")
        if analysis.odds and not analysis.odds_fresh:
            reasons.append("Odds zijn niet vers genoeg voor een officiële value pick.")
        if self.require_final_lineup and analysis.time_window == "FINAL" and not analysis.lineup_confirmed:
            reasons.append("Final scan zonder bevestigde line-ups; hooguit Watchlist, geen Value Pick.")
        if analysis.post_international_break and not analysis.lineup_confirmed:
            reasons.append("Eerste speelronde na interlandbreak zonder bevestigde line-up; Value Pick geblokkeerd.")
        if analysis.data_quality < self.min_data_quality:
            reasons.append(f"Datakwaliteit te laag: {analysis.data_quality:.1f}/10.")
        if analysis.confidence < self.min_confidence:
            reasons.append(f"Confidence te laag: {analysis.confidence:.1f}/10.")
        if analysis.risk_score > self.max_risk:
            reasons.append(f"Risico te hoog: {analysis.risk_score:.1f}/10.")
        if analysis.uncertainty_score > self.max_uncertainty:
            reasons.append(f"Onzekerheidsmarge te breed: {analysis.uncertainty_score:.1f}/10.")
        if value.selection and analysis.sharp_implied_movement:
            move = analysis.sharp_implied_movement.get(value.selection)
            if move is not None and move <= -0.025:
                reasons.append(f"Sharp markt beweegt tegen de selectie in ({move:.1%}); Value Pick geblokkeerd.")
        if value.status == "VALUE_CANDIDATE" and getattr(value, "stake_units", 0.0) < self.min_stake_units_for_value:
            reasons.append(f"Stake-indicatie te klein voor premium alert: {getattr(value, 'stake_units', 0.0):.2f}u.")
        if value.selection and value.selection in analysis.probability_intervals:
            low, high = analysis.probability_intervals[value.selection]
            # If the entire uncertainty interval does not beat the no-vig market, the edge is not robust.
            if low <= value.market_probability:
                reasons.append("Model-edge valt binnen de onzekerheidsmarge; geen robuuste value.")
        if value.status == "NO_BET":
            reasons.append(value.reason)
        return reasons
