from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, Iterable, List, Tuple
from football_agent.utils import clamp


@dataclass
class CalibrationRule:
    competition_key: str
    confidence_bucket: str
    edge_bucket: str
    adjustment: float
    sample_size: int


@dataclass
class CalibrationPoint:
    competition_key: str
    predicted_probability: float
    actual_outcome: int  # 1 if the predicted selection won, else 0
    confidence: float = 0.0
    edge: float = 0.0


@dataclass
class IsotonicSegment:
    low: float
    high: float
    calibrated_probability: float
    sample_size: int


class CalibrationModel:
    def __init__(self, min_samples: int = 100):
        self.min_samples = min_samples
        self.rules: Dict[Tuple[str, str, str], CalibrationRule] = {}
        self.isotonic_segments: Dict[str, List[IsotonicSegment]] = {}

    def bucket_confidence(self, confidence: float) -> str:
        if confidence < 5:
            return "0-5"
        if confidence < 7:
            return "5-7"
        if confidence < 8.5:
            return "7-8.5"
        return "8.5-10"

    def bucket_edge(self, edge: float) -> str:
        if edge < 0.02:
            return "0-2"
        if edge < 0.05:
            return "2-5"
        if edge < 0.08:
            return "5-8"
        return "8+"

    def adjustment(self, competition_key: str, confidence: float, edge: float) -> float:
        key = (competition_key, self.bucket_confidence(confidence), self.bucket_edge(edge))
        rule = self.rules.get(key)
        if not rule or rule.sample_size < self.min_samples:
            return 0.0
        # Hard cap prevents overreaction to cluster noise.
        return clamp(rule.adjustment, -0.025, 0.025)

    def fit_isotonic(self, points: Iterable[CalibrationPoint], min_samples: int | None = None) -> None:
        """Fit empirical monotonic calibration segments per competition.

        This is a lightweight Pool Adjacent Violators implementation. It has no
        sklearn dependency and remains inactive until enough historical points are
        available. It stores calibrated hit-rates by predicted probability ranges.
        """
        min_n = self.min_samples if min_samples is None else min_samples
        grouped: Dict[str, List[CalibrationPoint]] = {}
        for p in points:
            if 0.0 <= p.predicted_probability <= 1.0 and p.actual_outcome in {0, 1}:
                grouped.setdefault(p.competition_key, []).append(p)

        for comp, rows in grouped.items():
            if len(rows) < min_n:
                continue
            rows.sort(key=lambda r: r.predicted_probability)
            blocks = [
                {
                    "low": r.predicted_probability,
                    "high": r.predicted_probability,
                    "sum_y": float(r.actual_outcome),
                    "n": 1,
                }
                for r in rows
            ]
            i = 0
            while i < len(blocks) - 1:
                left_rate = blocks[i]["sum_y"] / blocks[i]["n"]
                right_rate = blocks[i + 1]["sum_y"] / blocks[i + 1]["n"]
                if left_rate <= right_rate:
                    i += 1
                    continue
                # Pool adjacent violators.
                blocks[i]["high"] = blocks[i + 1]["high"]
                blocks[i]["sum_y"] += blocks[i + 1]["sum_y"]
                blocks[i]["n"] += blocks[i + 1]["n"]
                del blocks[i + 1]
                if i > 0:
                    i -= 1
            self.isotonic_segments[comp] = [
                IsotonicSegment(
                    low=float(b["low"]),
                    high=float(b["high"]),
                    calibrated_probability=clamp(float(b["sum_y"]) / int(b["n"]), 0.01, 0.99),
                    sample_size=int(b["n"]),
                )
                for b in blocks
            ]

    def calibrate_probability(self, competition_key: str, predicted_probability: float) -> float:
        segments = self.isotonic_segments.get(competition_key) or []
        if not segments:
            return clamp(predicted_probability, 0.01, 0.99)
        p = clamp(predicted_probability, 0.01, 0.99)
        for seg in segments:
            if seg.low <= p <= seg.high:
                return seg.calibrated_probability
        # Smooth out-of-range extrapolation. Returning the closest segment as a
        # flat step creates EV jumps at the distribution tails. We extrapolate in
        # logit space using the slope of the nearest outer segment pair and cap the
        # result to avoid overconfident tails.
        if p < segments[0].low:
            return self._extrapolate_tail(p, segments[:2], left=True)
        return self._extrapolate_tail(p, segments[-2:], left=False)

    def _logit(self, p: float) -> float:
        p = clamp(p, 0.001, 0.999)
        return math.log(p / (1 - p))

    def _sigmoid(self, x: float) -> float:
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        z = math.exp(x)
        return z / (1.0 + z)

    def _extrapolate_tail(self, p: float, segs: List[IsotonicSegment], *, left: bool) -> float:
        if not segs:
            return clamp(p, 0.01, 0.99)
        if len(segs) == 1:
            return segs[0].calibrated_probability
        a, b = segs[0], segs[-1]
        x1 = (a.low + a.high) / 2.0
        x2 = (b.low + b.high) / 2.0
        y1 = self._logit(a.calibrated_probability)
        y2 = self._logit(b.calibrated_probability)
        if abs(x2 - x1) < 1e-9:
            return a.calibrated_probability if left else b.calibrated_probability
        slope = clamp((y2 - y1) / (x2 - x1), -8.0, 8.0)
        anchor_x = x1 if left else x2
        anchor_y = y1 if left else y2
        y = anchor_y + slope * (p - anchor_x)
        return clamp(self._sigmoid(y), 0.01, 0.99)

    def isotonic_adjustment(self, competition_key: str, predicted_probability: float) -> float:
        calibrated = self.calibrate_probability(competition_key, predicted_probability)
        return clamp(calibrated - predicted_probability, -0.04, 0.04)
