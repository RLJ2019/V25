from __future__ import annotations

import math
from typing import Dict, List, Optional
from football_agent.schemas import Fixture, MatchAnalysis, ModelProbabilities, FeatureAttribution, OddsSnapshot
from football_agent.utils import clamp
from .market_model import MarketModel
from .elo_model import EloModel
from .xg_model import XGModel, TeamFormStats
from .poisson_model import PoissonModel
from .injury_model import InjuryModel, PlayerAbsence
from .fatigue_model import FatigueModel
from .motivation_model import MotivationModel, StandingRow
from .referee_model import RefereeModel
from .calibration import CalibrationModel
from .uncertainty_model import UncertaintyModel
from .weighting import OverlayWeightManager


class EnsembleModel:
    def __init__(self):
        self.market = MarketModel()
        self.elo = EloModel()
        self.xg = XGModel()
        self.poisson = PoissonModel()
        self.injury = InjuryModel()
        self.fatigue = FatigueModel()
        self.motivation = MotivationModel()
        self.referee = RefereeModel()
        self.calibration = CalibrationModel()
        self.uncertainty = UncertaintyModel()
        self.weights = OverlayWeightManager()

    def analyze(
        self,
        fixture: Fixture,
        market_probabilities: Optional[Dict[str, float]] = None,
        odds: Optional[List[OddsSnapshot]] = None,
        home_form: Optional[TeamFormStats] = None,
        away_form: Optional[TeamFormStats] = None,
        home_absences: Optional[List[PlayerAbsence]] = None,
        away_absences: Optional[List[PlayerAbsence]] = None,
        home_previous_match_utc: Optional[str] = None,
        away_previous_match_utc: Optional[str] = None,
        home_europe_midweek: bool = False,
        away_europe_midweek: bool = False,
        home_travel_km: float = 0.0,
        away_travel_km: float = 0.0,
        standings: Optional[List[StandingRow]] = None,
        competition_type: str = "league",
        market_cleansing_failed: bool = False,
        time_window: str = "UNKNOWN",
        lineup_confirmed: bool = False,
        odds_fresh: bool = False,
        data_snapshot_id: Optional[str] = None,
        sharp_implied_movement: Optional[Dict[str, float]] = None,
        post_international_break: bool = False,
        home_is_promoted: bool = False,
        away_is_promoted: bool = False,
        promoted_elo: float | None = None,
    ) -> MatchAnalysis:
        odds = odds or []
        sharp_implied_movement = sharp_implied_movement or {}
        notes: List[str] = []
        market_probabilities_are_fallback = False
        if market_probabilities is None:
            # Conservative market-neutral fallback. It is only for keeping the report alive;
            # value picks are blocked by NoBetRules whenever this fallback is used.
            market_probabilities = {"HOME": 0.36, "DRAW": 0.28, "AWAY": 0.36}
            market_probabilities_are_fallback = True
            notes.append("Geen bruikbare gecleande marktbaseline: fallback gebruikt. Value Pick wordt geblokkeerd.")

        if post_international_break:
            notes.append("Eerste speelronde na interlandperiode: onzekerheid verhoogd en confidence gecapt.")

        home_form = home_form or TeamFormStats()
        away_form = away_form or TeamFormStats()
        home_xg = self.xg.estimate_team_xg(home_form, away_form, fallback=1.32, as_of_utc=fixture.kickoff_utc)
        away_xg = self.xg.estimate_team_xg(away_form, home_form, fallback=1.10, as_of_utc=fixture.kickoff_utc)
        home_injury_penalty = self.injury.team_impact(home_absences or [])
        away_injury_penalty = self.injury.team_impact(away_absences or [])
        home_fatigue = self.fatigue.penalty(fixture.kickoff_utc, home_previous_match_utc, home_europe_midweek, home_travel_km, home_europe_midweek)
        away_fatigue = self.fatigue.penalty(fixture.kickoff_utc, away_previous_match_utc, away_europe_midweek, away_travel_km, away_europe_midweek)

        # Apply xG adjustments from injury/fatigue impact. Absence of away players benefits home probability and vice versa.
        adj_home_xg = clamp(home_xg * (1 - home_injury_penalty - home_fatigue) * (1 + away_injury_penalty * 0.65 + away_fatigue * 0.45), 0.15, 4.5)
        adj_away_xg = clamp(away_xg * (1 - away_injury_penalty - away_fatigue) * (1 + home_injury_penalty * 0.65 + home_fatigue * 0.45), 0.15, 4.5)
        projection = self.poisson.project(adj_home_xg, adj_away_xg, use_dixon_coles=True)

        # Explicit xG feature attribution. Positive means the adjusted xG gap supports HOME; negative supports AWAY.
        home_xg_delta = self.xg.adjustment_pp(adj_home_xg, adj_away_xg)
        away_xg_delta = -home_xg_delta
        draw_xg_delta = -abs(home_xg_delta) * 0.30
        motivation_delta = self.motivation.relative_adjustment(
            fixture.home_team,
            fixture.away_team,
            standings=standings,
            competition_type=competition_type,
        )

        home_attr = self._build_attribution(
            "HOME", fixture, market_probabilities, projection.outcome_probabilities,
            xg_delta=home_xg_delta,
            injury_delta=away_injury_penalty - home_injury_penalty,
            fatigue_delta=away_fatigue - home_fatigue,
            motivation_delta=motivation_delta.get("HOME", 0.0),
            competition_key=fixture.competition_key,
            home_is_promoted=home_is_promoted,
            away_is_promoted=away_is_promoted,
            promoted_elo=promoted_elo,
        )
        away_attr = self._build_attribution(
            "AWAY", fixture, market_probabilities, projection.outcome_probabilities,
            xg_delta=away_xg_delta,
            injury_delta=home_injury_penalty - away_injury_penalty,
            fatigue_delta=home_fatigue - away_fatigue,
            motivation_delta=motivation_delta.get("AWAY", 0.0),
            competition_key=fixture.competition_key,
            home_is_promoted=home_is_promoted,
            away_is_promoted=away_is_promoted,
            promoted_elo=promoted_elo,
        )
        draw_attr = self._build_attribution(
            "DRAW", fixture, market_probabilities, projection.outcome_probabilities,
            xg_delta=draw_xg_delta,
            injury_delta=-abs(away_injury_penalty - home_injury_penalty) * 0.25,
            fatigue_delta=-abs(away_fatigue - home_fatigue) * 0.15,
            motivation_delta=motivation_delta.get("DRAW", 0.0),
            competition_key=fixture.competition_key,
            home_is_promoted=home_is_promoted,
            away_is_promoted=away_is_promoted,
            promoted_elo=promoted_elo,
        )

        raw = {"HOME": home_attr.final_probability, "DRAW": draw_attr.final_probability, "AWAY": away_attr.final_probability}
        total = sum(max(0.001, v) for v in raw.values())
        probs = {k: clamp(max(0.001, v) / total, 0.001, 0.95) for k, v in raw.items()}
        # Normalize after clamp.
        total2 = sum(probs.values())
        probs = {k: v / total2 for k, v in probs.items()}
        home_attr.final_probability = probs["HOME"]
        draw_attr.final_probability = probs["DRAW"]
        away_attr.final_probability = probs["AWAY"]

        xg_available = any(v is not None for v in [home_form.xg_for_last5, away_form.xg_for_last5, home_form.xg_against_last5, away_form.xg_against_last5]) or bool(home_form.recent_matches or away_form.recent_matches)
        standings_available = bool(standings)
        data_quality = self._data_quality(bool(odds), xg_available, bool(home_absences or away_absences), market_probabilities_are_fallback, market_cleansing_failed, standings_available)
        edge_signal = max(abs(probs[k] - market_probabilities.get(k, probs[k])) for k in probs)
        confidence = self._confidence(data_quality, edge_signal, odds_available=bool(odds), market_clean=not (market_probabilities_are_fallback or market_cleansing_failed))
        if post_international_break:
            confidence = min(confidence, 7.0)
        intervals, uncertainty_score = self.uncertainty.estimate(
            ModelProbabilities(home=probs["HOME"], draw=probs["DRAW"], away=probs["AWAY"]),
            data_quality=data_quality,
            confidence=confidence,
            time_window=time_window,
            lineup_confirmed=lineup_confirmed,
            odds_fresh=odds_fresh,
            market_clean=not (market_probabilities_are_fallback or market_cleansing_failed),
            attribution_matrix={
                "HOME": home_attr.as_dict(),
                "DRAW": draw_attr.as_dict(),
                "AWAY": away_attr.as_dict(),
            },
            sharp_implied_movement=sharp_implied_movement,
            post_international_break=post_international_break,
        )
        risk = clamp(10 - confidence + (1.0 if not odds else 0.0) + (1.2 if market_probabilities_are_fallback or market_cleansing_failed else 0.0) + (0.8 if post_international_break else 0.0) + uncertainty_score * 0.15, 0, 10)

        return MatchAnalysis(
            fixture=fixture,
            model_probabilities=ModelProbabilities(home=probs["HOME"], draw=probs["DRAW"], away=probs["AWAY"]),
            market_probabilities=market_probabilities,
            attribution_home=home_attr,
            attribution_draw=draw_attr,
            attribution_away=away_attr,
            poisson=projection,
            data_quality=data_quality,
            confidence=confidence,
            risk_score=risk,
            notes=notes,
            odds=odds,
            market_cleansing_failed=market_cleansing_failed,
            market_probabilities_are_fallback=market_probabilities_are_fallback,
            probability_intervals=intervals,
            uncertainty_score=uncertainty_score,
            data_snapshot_id=data_snapshot_id,
            time_window=time_window,
            lineup_confirmed=lineup_confirmed,
            odds_fresh=odds_fresh,
            sharp_implied_movement=sharp_implied_movement,
            post_international_break=post_international_break,
            home_is_promoted=home_is_promoted,
            away_is_promoted=away_is_promoted,
        )

    def _build_attribution(
        self,
        selection: str,
        fixture: Fixture,
        market_probs: Dict[str, float],
        poisson_probs: Dict[str, float],
        xg_delta: float,
        injury_delta: float,
        fatigue_delta: float,
        motivation_delta: float = 0.0,
        competition_key: Optional[str] = None,
        home_is_promoted: bool = False,
        away_is_promoted: bool = False,
        promoted_elo: float | None = None,
    ) -> FeatureAttribution:
        base = clamp(market_probs.get(selection, 1 / 3), 0.01, 0.99)
        elo_adj = self.elo.adjustment_pp(
            fixture.home_team,
            fixture.away_team,
            home_is_promoted=home_is_promoted,
            away_is_promoted=away_is_promoted,
            promoted_elo=promoted_elo,
        )
        if selection == "AWAY":
            elo_adj = -elo_adj
        if selection == "DRAW":
            elo_adj = -abs(elo_adj) * 0.35
        xg_adj = clamp(xg_delta, -0.08, 0.08)
        poisson_adj = clamp((poisson_probs.get(selection, base) - base) * 0.28, -0.06, 0.06)
        injury_adj = clamp(injury_delta * 0.55, -0.06, 0.06)
        fatigue_adj = clamp(fatigue_delta * 0.45, -0.05, 0.05)
        home_advantage = 0.015 if selection == "HOME" else -0.008 if selection == "AWAY" else -0.004
        motivation_adj = clamp(motivation_delta, -0.025, 0.025)
        referee_adj = 0.0
        calibration_adj = self.calibration.adjustment(fixture.competition_key, 7.0, 0.04)

        # V25.0.9: apply adjustments in order-invariant log-odds space.
        # Stored values are effective probability-point contributions for reporting.
        effective, final = self._apply_logit_attribution(
            base,
            [
                ("elo_adjustment", self.weights.apply(competition_key, "elo_adjustment", elo_adj)),
                ("xg_form_adjustment", self.weights.apply(competition_key, "xg_form_adjustment", xg_adj)),
                ("poisson_adjustment", self.weights.apply(competition_key, "poisson_adjustment", poisson_adj)),
                ("home_advantage", self.weights.apply(competition_key, "home_advantage", home_advantage)),
                ("injury_impact", self.weights.apply(competition_key, "injury_impact", injury_adj)),
                ("fatigue_impact", self.weights.apply(competition_key, "fatigue_impact", fatigue_adj)),
                ("motivation_impact", self.weights.apply(competition_key, "motivation_impact", motivation_adj)),
                ("referee_impact", self.weights.apply(competition_key, "referee_impact", referee_adj)),
                ("calibration_adjustment", self.weights.apply(competition_key, "calibration_adjustment", calibration_adj)),
            ],
        )
        return FeatureAttribution(
            market_baseline=base,
            elo_adjustment=effective["elo_adjustment"],
            xg_form_adjustment=effective["xg_form_adjustment"],
            poisson_adjustment=effective["poisson_adjustment"],
            home_advantage=effective["home_advantage"],
            injury_impact=effective["injury_impact"],
            fatigue_impact=effective["fatigue_impact"],
            motivation_impact=effective["motivation_impact"],
            referee_impact=effective["referee_impact"],
            calibration_adjustment=effective["calibration_adjustment"],
            final_probability=clamp(final, 0.02, 0.95),
        )

    def _apply_logit_attribution(self, base: float, contributions: List[tuple[str, float]]) -> tuple[Dict[str, float], float]:
        # V25.0.9: order-invariant logit overlay. Earlier builds transformed each
        # probability-point feature sequentially, making the final result slightly
        # dependent on feature order. We now convert every contribution using the
        # same baseline slope, sum pure logit deltas, and only then transform back.
        base = clamp(base, 0.01, 0.99)
        base_logit = self._logit(base)
        baseline_slope = max(base * (1 - base), 0.04)
        deltas: List[tuple[str, float, float]] = []
        for name, pp in contributions:
            delta_logit = clamp(pp / baseline_slope, -0.85, 0.85)
            single_effect = clamp(self._sigmoid(base_logit + delta_logit), 0.01, 0.99) - base
            deltas.append((name, delta_logit, single_effect))
        final = clamp(self._sigmoid(base_logit + sum(d for _, d, _ in deltas)), 0.01, 0.99)
        total_effect = final - base
        raw_sum = sum(effect for _, _, effect in deltas)
        effective: Dict[str, float] = {}
        if abs(raw_sum) < 1e-12:
            for name, _, _ in deltas:
                effective[name] = 0.0
        else:
            for name, _, effect in deltas:
                effective[name] = effect / raw_sum * total_effect
        return effective, final

    def _logit(self, p: float) -> float:
        p = clamp(p, 0.001, 0.999)
        return math.log(p / (1 - p))

    def _sigmoid(self, x: float) -> float:
        if x >= 0:
            z = math.exp(-x)
            return 1 / (1 + z)
        z = math.exp(x)
        return z / (1 + z)

    def _data_quality(self, odds_available: bool, xg_available: bool, injuries_available: bool, market_fallback: bool, market_failed: bool, standings_available: bool = False) -> float:
        score = 4.0
        if odds_available:
            score += 2.4
        if xg_available:
            score += 1.5
        if injuries_available:
            score += 1.0
        if standings_available:
            score += 0.4
        score += 0.8  # fixture/basic data
        if market_fallback or market_failed:
            score -= 2.0
        return clamp(score, 0.0, 10.0)

    def _confidence(self, data_quality: float, edge_signal: float, odds_available: bool, market_clean: bool) -> float:
        score = data_quality * 0.55 + min(edge_signal * 100, 10) * 0.35
        if odds_available:
            score += 1.0
        else:
            score -= 1.2
        if not market_clean:
            score -= 1.5
        return clamp(score, 0.0, 10.0)
