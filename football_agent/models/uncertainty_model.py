from __future__ import annotations

import random
from typing import Dict, Tuple, Optional
from football_agent.schemas import ModelProbabilities
from football_agent.utils import clamp


class UncertaintyModel:
    """Conservative uncertainty intervals around model probabilities.

    V25.0.4 adds a deterministic Monte Carlo/bootstrap option. If feature
    attribution is supplied, the model perturbs attribution components inside
    data-quality dependent confidence bands and builds empirical probability
    ranges. If attribution is absent, it falls back to the V25.0.3 rule matrix.
    """

    def estimate(
        self,
        probabilities: ModelProbabilities,
        *,
        data_quality: float,
        confidence: float,
        time_window: str,
        lineup_confirmed: bool,
        odds_fresh: bool,
        market_clean: bool,
        attribution_matrix: Optional[Dict[str, Dict[str, float]]] = None,
        sharp_implied_movement: Optional[Dict[str, float]] = None,
        post_international_break: bool = False,
        iterations: int = 600,
    ) -> tuple[Dict[str, Tuple[float, float]], float]:
        base_width = self._rule_half_width(
            data_quality=data_quality,
            confidence=confidence,
            time_window=time_window,
            lineup_confirmed=lineup_confirmed,
            odds_fresh=odds_fresh,
            market_clean=market_clean,
            sharp_implied_movement=sharp_implied_movement or {},
            post_international_break=post_international_break,
        )
        if attribution_matrix:
            return self._bootstrap_intervals(
                probabilities,
                attribution_matrix=attribution_matrix,
                base_width=base_width,
                data_quality=data_quality,
                confidence=confidence,
                iterations=iterations,
            )
        return self._rule_intervals(probabilities, base_width)

    def _rule_half_width(
        self,
        *,
        data_quality: float,
        confidence: float,
        time_window: str,
        lineup_confirmed: bool,
        odds_fresh: bool,
        market_clean: bool,
        sharp_implied_movement: Dict[str, float],
        post_international_break: bool = False,
    ) -> float:
        base_width = 0.035
        quality_penalty = clamp((8.5 - data_quality) * 0.012, 0.0, 0.08)
        confidence_penalty = clamp((8.0 - confidence) * 0.010, 0.0, 0.07)
        freshness_penalty = 0.025 if not odds_fresh else 0.0
        market_penalty = 0.040 if not market_clean else 0.0
        final_lineup_penalty = 0.035 if time_window == "FINAL" and not lineup_confirmed else 0.0
        early_penalty = 0.020 if time_window == "EARLY" else 0.0
        international_break_penalty = 0.0
        if post_international_break:
            # First club round after international breaks carries travel, rotation and
            # minor-injury variance. Apply a 25% uplift to the base uncertainty.
            international_break_penalty = base_width * 0.25
        adverse_sharp_move_penalty = 0.0
        if sharp_implied_movement:
            # Any strong sharp disagreement increases uncertainty globally; the selected side
            # can still be blocked more explicitly in NoBetRules.
            adverse_sharp_move_penalty = clamp(max(abs(v) for v in sharp_implied_movement.values()) * 0.25, 0.0, 0.035)
        return clamp(
            base_width + quality_penalty + confidence_penalty + freshness_penalty + market_penalty + final_lineup_penalty + early_penalty + international_break_penalty + adverse_sharp_move_penalty,
            0.03,
            0.20,
        )

    def _rule_intervals(self, probabilities: ModelProbabilities, half_width: float) -> tuple[Dict[str, Tuple[float, float]], float]:
        probs = probabilities.as_dict()
        intervals = {
            k: (clamp(v - half_width, 0.001, 0.999), clamp(v + half_width, 0.001, 0.999))
            for k, v in probs.items()
        }
        return intervals, clamp((half_width / 0.20) * 10.0, 0.0, 10.0)

    def _bootstrap_intervals(
        self,
        probabilities: ModelProbabilities,
        *,
        attribution_matrix: Dict[str, Dict[str, float]],
        base_width: float,
        data_quality: float,
        confidence: float,
        iterations: int,
    ) -> tuple[Dict[str, Tuple[float, float]], float]:
        rng = random.Random(2504)
        feature_names = [
            "elo_adjustment", "xg_form_adjustment", "poisson_adjustment", "home_advantage",
            "injury_impact", "fatigue_impact", "motivation_impact", "referee_impact", "calibration_adjustment",
        ]
        # Weak data means feature contributions are less certain.
        contribution_noise = clamp(base_width * (1.15 + (8.0 - data_quality) * 0.08 + (8.0 - confidence) * 0.06), 0.015, 0.12)
        sims: Dict[str, list[float]] = {"HOME": [], "DRAW": [], "AWAY": []}
        for _ in range(max(100, iterations)):
            raw: Dict[str, float] = {}
            for sel in sims:
                attr = attribution_matrix.get(sel, {})
                p = float(attr.get("market_baseline", probabilities.as_dict().get(sel, 1/3)))
                for name in feature_names:
                    contrib = float(attr.get(name, 0.0))
                    perturbed = rng.gauss(contrib, contribution_noise * max(0.35, min(1.35, abs(contrib) / 0.025 if contrib else 0.75)))
                    p += perturbed
                raw[sel] = clamp(p, 0.001, 0.999)
            total = sum(raw.values()) or 1.0
            for sel, val in raw.items():
                sims[sel].append(val / total)
        intervals: Dict[str, Tuple[float, float]] = {}
        max_width = base_width * 2
        for sel, values in sims.items():
            values.sort()
            lo = values[int(0.10 * (len(values)-1))]
            hi = values[int(0.90 * (len(values)-1))]
            center = probabilities.as_dict()[sel]
            # Preserve conservative rule width as a floor.
            lo = min(lo, center - base_width)
            hi = max(hi, center + base_width)
            intervals[sel] = (clamp(lo, 0.001, 0.999), clamp(hi, 0.001, 0.999))
            max_width = max(max_width, intervals[sel][1] - intervals[sel][0])
        uncertainty_score = clamp((max_width / 0.40) * 10.0, 0.0, 10.0)
        return intervals, uncertainty_score
