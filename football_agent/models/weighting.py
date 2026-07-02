from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


DEFAULT_MULTIPLIERS: Dict[str, float] = {
    "elo_adjustment": 1.0,
    "xg_form_adjustment": 1.0,
    "poisson_adjustment": 1.0,
    "home_advantage": 1.0,
    "injury_impact": 1.0,
    "fatigue_impact": 1.0,
    "motivation_impact": 1.0,
    "referee_impact": 1.0,
    "calibration_adjustment": 1.0,
}


@dataclass
class OverlayWeightManager:
    """Competition-aware overlay multipliers.

    Defaults preserve V25.0.3 behaviour. Offline training can write
    config/learned_model_weights.json to tune the multipliers per competition
    once sufficient backtest/live data exists. Multipliers are intentionally
    bounded to avoid overfitting.
    """

    path: str | Path = "football_agent/config/learned_model_weights.json"
    fallback: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_MULTIPLIERS))

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self._payload: Dict = {}
        if self.path.exists():
            try:
                self._payload = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._payload = {}

    def multipliers_for(self, competition_key: Optional[str]) -> Dict[str, float]:
        out = dict(self.fallback)
        global_weights = self._payload.get("global", {}) if isinstance(self._payload, dict) else {}
        comp_weights = (self._payload.get("competitions", {}) or {}).get(competition_key or "", {}) if isinstance(self._payload, dict) else {}
        for source in (global_weights, comp_weights):
            for k, v in (source or {}).items():
                try:
                    out[k] = min(1.75, max(0.25, float(v)))
                except (TypeError, ValueError):
                    pass
        return out

    def apply(self, competition_key: Optional[str], feature_name: str, value: float) -> float:
        return value * self.multipliers_for(competition_key).get(feature_name, 1.0)
