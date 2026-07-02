from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class Team:
    id: Optional[str]
    name: str
    short_name: Optional[str] = None
    country: Optional[str] = None


@dataclass
class Competition:
    key: str
    name: str
    country: str
    type: str
    football_data_code: Optional[str]
    api_football_league_id: Optional[int]
    priority: int = 1
    # V25.0.6: competition-specific trading guardrails.
    # min_edge_threshold is financial EV threshold for all markets unless a market-specific
    # override exists in market_min_edge_thresholds.
    min_edge_threshold: Optional[float] = None
    market_min_edge_thresholds: Dict[str, float] = field(default_factory=dict)
    # Bayesian Elo prior for newly promoted teams. Names are normalized in run_daily.
    promoted_teams: List[str] = field(default_factory=list)
    promoted_elo: float = 1435.0


@dataclass
class Fixture:
    id: str
    competition_key: str
    competition_name: str
    home_team: str
    away_team: str
    kickoff_utc: str
    status: str = "SCHEDULED"
    venue: Optional[str] = None
    city: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    source: str = "unknown"
    api_football_fixture_id: Optional[int] = None
    football_data_match_id: Optional[int] = None

    @property
    def matchup(self) -> str:
        return f"{self.home_team} vs {self.away_team}"


@dataclass
class OddsSnapshot:
    bookmaker: str
    market: str
    selection: str
    odds: float
    timestamp_utc: str
    profile: str = "unknown"
    opening_odds: Optional[float] = None
    closing_odds: Optional[float] = None


@dataclass
class ModelProbabilities:
    home: float
    draw: float
    away: float

    def as_dict(self) -> Dict[str, float]:
        return {"HOME": self.home, "DRAW": self.draw, "AWAY": self.away}


@dataclass
class PoissonProjection:
    home_xg: float
    away_xg: float
    most_likely_score: str
    score_probability: float
    outcome_probabilities: Dict[str, float]
    over_under: Dict[str, float]
    btts: Dict[str, float]


@dataclass
class FeatureAttribution:
    market_baseline: float
    elo_adjustment: float = 0.0
    xg_form_adjustment: float = 0.0
    poisson_adjustment: float = 0.0
    home_advantage: float = 0.0
    injury_impact: float = 0.0
    fatigue_impact: float = 0.0
    motivation_impact: float = 0.0
    referee_impact: float = 0.0
    calibration_adjustment: float = 0.0
    final_probability: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class MatchAnalysis:
    fixture: Fixture
    model_probabilities: ModelProbabilities
    market_probabilities: Dict[str, float]
    attribution_home: FeatureAttribution
    attribution_draw: FeatureAttribution
    attribution_away: FeatureAttribution
    poisson: Optional[PoissonProjection]
    data_quality: float
    confidence: float
    risk_score: float
    notes: List[str] = field(default_factory=list)
    odds: List[OddsSnapshot] = field(default_factory=list)
    market_cleansing_failed: bool = False
    market_probabilities_are_fallback: bool = False
    probability_intervals: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    uncertainty_score: float = 0.0
    data_snapshot_id: Optional[str] = None
    time_window: str = "UNKNOWN"
    lineup_confirmed: bool = False
    odds_fresh: bool = False
    sharp_implied_movement: Dict[str, float] = field(default_factory=dict)
    post_international_break: bool = False
    home_is_promoted: bool = False
    away_is_promoted: bool = False


@dataclass
class ValueDecision:
    selection: str
    model_probability: float
    market_probability: float
    odds: Optional[float]
    # edge is the financial expected value / yield edge: (model_probability * decimal_odds) - 1.
    # probability_edge keeps the pure probability delta versus the no-vig market.
    edge: float
    fair_odds: Optional[float]
    status: str
    reason: str
    # Minimum decimal odds required for an official value pick after applying the
    # configured financial EV threshold. This is stricter than fair_odds.
    min_acceptable_odds: Optional[float] = None
    bookmaker: Optional[str] = None
    probability_edge: float = 0.0
    expected_value: float = 0.0
    market: str = "1X2"
    raw_kelly_fraction: float = 0.0
    fractional_kelly: float = 0.0
    stake_units: float = 0.0
    stake_reason: str = ""
    # Market-baseline transparency for premium Telegram alerts.
    # sharp_fair_odds is based on the cleaned market baseline (preferably sharp market).
    baseline_source: str = "unknown"
    sharp_market_probability: float = 0.0
    sharp_fair_odds: Optional[float] = None
    selected_odds_profile: str = "unknown"


@dataclass
class PickDecision:
    fixture: Fixture
    status: str
    advice: str
    selection: Optional[str]
    value_decision: Optional[ValueDecision]
    confidence: float
    data_quality: float
    risk_score: float
    explanation_facts: Dict[str, Any]
    created_at_utc: str = field(default_factory=utc_now_iso)
    model_version: str = "unknown"
    config_version: str = "unknown"
    feature_set_version: str = "unknown"
    calibration_version: str = "unknown"
    data_snapshot_id: Optional[str] = None
    time_window: str = "UNKNOWN"
    lineup_confirmed: bool = False
    uncertainty_score: float = 0.0
    probability_interval_low: Optional[float] = None
    probability_interval_high: Optional[float] = None
    post_international_break: bool = False
    home_is_promoted: bool = False
    away_is_promoted: bool = False
    raw_kelly_fraction: float = 0.0
    fractional_kelly: float = 0.0
    stake_units: float = 0.0
    stake_reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
