from __future__ import annotations

from typing import Dict, Optional
from football_agent.schemas import ModelProbabilities, OddsSnapshot, ValueDecision


class ValueEngine:
    """Financial value engine.

    Primary edge = financial expected value / yield edge:
        expected_value = (model_probability * decimal_odds) - 1

    V25 evaluates 1X2 plus derived markets such as OVER_UNDER_2_5 and BTTS.
    V25.0.9 also carries market-baseline transparency forward into the decision
    so Telegram can show whether a pick is beating the cleaned sharp/no-vig line.
    """

    def __init__(self, min_edge: float = 0.04, min_probability_edge: float = 0.0):
        self.min_edge = min_edge
        self.min_probability_edge = min_probability_edge

    def evaluate_selection(
        self,
        model: ModelProbabilities,
        market_probs: Dict[str, float],
        odds: Optional[OddsSnapshot],
        *,
        custom_min_edge: Optional[float] = None,
        min_edge_by_market: Optional[Dict[str, float]] = None,
        baseline_source_by_market: Optional[Dict[str, str]] = None,
    ) -> ValueDecision:
        if odds is None:
            return self._no_odds_decision()
        return self.evaluate_selection_from_maps(
            model.as_dict(),
            market_probs,
            odds,
            custom_min_edge=custom_min_edge,
            min_edge_by_market=min_edge_by_market,
            baseline_source_by_market=baseline_source_by_market,
        )

    def _threshold_for(
        self,
        odds: OddsSnapshot,
        custom_min_edge: Optional[float],
        min_edge_by_market: Optional[Dict[str, float]],
    ) -> float:
        if min_edge_by_market and odds.market in min_edge_by_market:
            return float(min_edge_by_market[odds.market])
        if custom_min_edge is not None:
            return float(custom_min_edge)
        return self.min_edge

    def evaluate_selection_from_maps(
        self,
        model_probs: Dict[str, float],
        market_probs: Dict[str, float],
        odds: Optional[OddsSnapshot],
        *,
        custom_min_edge: Optional[float] = None,
        min_edge_by_market: Optional[Dict[str, float]] = None,
        baseline_source_by_market: Optional[Dict[str, str]] = None,
    ) -> ValueDecision:
        if odds is None:
            return self._no_odds_decision()
        model_prob = model_probs.get(odds.selection, 0.0)
        market_prob = market_probs.get(odds.selection, 0.0)
        probability_edge = model_prob - market_prob
        expected_value = (model_prob * odds.odds) - 1.0 if odds.odds else -1.0
        fair_odds = 1.0 / model_prob if model_prob > 0 else None
        current_min_edge = self._threshold_for(odds, custom_min_edge, min_edge_by_market)
        min_acceptable_odds = ((1.0 + current_min_edge) / model_prob) if model_prob > 0 else None
        odds_above_value_floor = bool(min_acceptable_odds is not None and odds.odds >= min_acceptable_odds)
        baseline_source = (baseline_source_by_market or {}).get(odds.market, "unknown")
        market_fair_odds = (1.0 / market_prob) if market_prob > 0 else None

        if expected_value >= current_min_edge and probability_edge >= self.min_probability_edge and odds_above_value_floor:
            status = "VALUE_CANDIDATE"
            reason = (
                f"Financiële EV {expected_value:.1%} boven minimum {current_min_edge:.1%}; "
                f"min. odds {min_acceptable_odds:.2f}; probability edge {probability_edge:.1%}; "
                f"markt={odds.market}; baseline={baseline_source}."
            )
        elif expected_value > 0 and probability_edge >= self.min_probability_edge:
            status = "WATCHLIST"
            threshold_txt = f"min. odds {min_acceptable_odds:.2f}" if min_acceptable_odds else "geen min. odds"
            reason = (
                f"Positieve EV {expected_value:.1%}, maar onder value-pick grens {current_min_edge:.1%} "
                f"({threshold_txt}); markt={odds.market}; baseline={baseline_source}."
            )
        else:
            status = "NO_BET"
            reason = "Geen positieve financiële expected value na margin cleansing."
        return ValueDecision(
            selection=odds.selection,
            model_probability=model_prob,
            market_probability=market_prob,
            odds=odds.odds,
            edge=expected_value,
            fair_odds=fair_odds,
            min_acceptable_odds=min_acceptable_odds,
            status=status,
            reason=reason,
            bookmaker=odds.bookmaker,
            probability_edge=probability_edge,
            expected_value=expected_value,
            market=odds.market,
            baseline_source=baseline_source,
            sharp_market_probability=market_prob,
            sharp_fair_odds=market_fair_odds,
            selected_odds_profile=odds.profile or "unknown",
        )

    def best_value(
        self,
        model: ModelProbabilities,
        market_probs: Dict[str, float],
        best_odds: Dict[str, OddsSnapshot],
        *,
        custom_min_edge: Optional[float] = None,
        min_edge_by_market: Optional[Dict[str, float]] = None,
        baseline_source_by_market: Optional[Dict[str, str]] = None,
    ) -> ValueDecision:
        return self.best_value_from_maps(
            model.as_dict(),
            market_probs,
            best_odds,
            custom_min_edge=custom_min_edge,
            min_edge_by_market=min_edge_by_market,
            baseline_source_by_market=baseline_source_by_market,
        )

    def best_value_from_maps(
        self,
        model_probs: Dict[str, float],
        market_probs: Dict[str, float],
        best_odds: Dict[str, OddsSnapshot],
        *,
        custom_min_edge: Optional[float] = None,
        min_edge_by_market: Optional[Dict[str, float]] = None,
        baseline_source_by_market: Optional[Dict[str, str]] = None,
    ) -> ValueDecision:
        decisions = [
            self.evaluate_selection_from_maps(
                model_probs,
                market_probs,
                o,
                custom_min_edge=custom_min_edge,
                min_edge_by_market=min_edge_by_market,
                baseline_source_by_market=baseline_source_by_market,
            )
            for o in best_odds.values()
        ]
        if not decisions:
            return self._no_odds_decision()
        return max(decisions, key=lambda d: (d.expected_value, d.probability_edge))

    def _no_odds_decision(self) -> ValueDecision:
        return ValueDecision(
            selection="NONE",
            model_probability=0.0,
            market_probability=0.0,
            odds=None,
            edge=0.0,
            fair_odds=None,
            min_acceptable_odds=None,
            status="NO_BET",
            reason="Geen odds beschikbaar, dus geen valueberekening mogelijk.",
            probability_edge=0.0,
            expected_value=0.0,
            market="NONE",
            baseline_source="none",
            sharp_market_probability=0.0,
            sharp_fair_odds=None,
            selected_odds_profile="unknown",
        )
