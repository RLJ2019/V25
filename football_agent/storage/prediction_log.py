from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List, Dict
from football_agent.schemas import PickDecision


class PredictionLog:
    FIELDNAMES = [
        "created_at_utc", "fixture_id", "competition_key", "competition_name", "home_team", "away_team", "kickoff_utc",
        "status", "selection", "advice", "confidence", "data_quality", "risk_score", "uncertainty_score",
        "probability_interval_low", "probability_interval_high", "time_window", "lineup_confirmed", "data_snapshot_id",
        "model_version", "config_version", "feature_set_version", "calibration_version",
        "model_home", "model_draw", "model_away", "market_home", "market_draw", "market_away",
        "selected_model_probability", "selected_market_probability",
        "edge", "probability_edge", "expected_value", "odds", "bookmaker", "market", "fair_odds",
        "raw_kelly_fraction", "fractional_kelly", "stake_units", "stake_reason", "post_international_break",
        "selected_attr_elo", "selected_attr_xg", "selected_attr_poisson", "selected_attr_injury",
        "selected_attr_fatigue", "selected_attr_motivation", "selected_attr_calibration", "sharp_movement_selection",
    ]

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, picks: Iterable[PickDecision]) -> None:
        self._ensure_header_compatible()
        exists = self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            if not exists:
                writer.writeheader()
            for p in picks:
                writer.writerow(self._row(p))

    def _ensure_header_compatible(self) -> None:
        """Rewrite existing CSV when new columns are introduced.

        GitHub Actions restores output/ from cache across runs. V25 hotfixes can
        add audit columns to prediction_log.csv, while the cached file still has
        the old header. Appending a wider row to an old header makes csv.DictReader
        place trailing values under a None key, which then breaks shadow parity.
        Keep old rows, add missing columns as empty strings, and write a fresh
        header before appending.
        """
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        with self.path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            existing_fieldnames = list(reader.fieldnames or [])
            if existing_fieldnames == self.FIELDNAMES:
                return
            rows = list(reader)
        if all(field in existing_fieldnames for field in self.FIELDNAMES):
            # Reorder canonical header if needed.
            pass
        with self.path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            for row in rows:
                clean = {field: row.get(field, "") for field in self.FIELDNAMES}
                writer.writerow(clean)

    def read(self) -> List[Dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open("r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _row(self, p: PickDecision) -> Dict:
        value = p.value_decision
        facts = p.explanation_facts
        mp = facts.get("model_probabilities", {})
        mk = facts.get("market_probabilities", {})
        selected_attr = {}
        sel = p.selection or ""
        if sel in {"HOME", "DRAW", "AWAY"}:
            selected_attr = (facts.get("attribution", {}) or {}).get(sel, {}) or {}
        sharp_move = (facts.get("sharp_implied_movement", {}) or {}).get(sel, "")
        return {
            "created_at_utc": p.created_at_utc,
            "fixture_id": p.fixture.id,
            "competition_key": p.fixture.competition_key,
            "competition_name": p.fixture.competition_name,
            "home_team": p.fixture.home_team,
            "away_team": p.fixture.away_team,
            "kickoff_utc": p.fixture.kickoff_utc,
            "status": p.status,
            "selection": p.selection or "",
            "advice": p.advice,
            "confidence": f"{p.confidence:.2f}",
            "data_quality": f"{p.data_quality:.2f}",
            "risk_score": f"{p.risk_score:.2f}",
            "uncertainty_score": f"{p.uncertainty_score:.2f}",
            "probability_interval_low": f"{p.probability_interval_low:.6f}" if p.probability_interval_low is not None else "",
            "probability_interval_high": f"{p.probability_interval_high:.6f}" if p.probability_interval_high is not None else "",
            "time_window": p.time_window,
            "lineup_confirmed": str(p.lineup_confirmed),
            "data_snapshot_id": p.data_snapshot_id or "",
            "model_version": p.model_version,
            "config_version": p.config_version,
            "feature_set_version": p.feature_set_version,
            "calibration_version": p.calibration_version,
            "model_home": f"{mp.get('HOME', 0):.6f}",
            "model_draw": f"{mp.get('DRAW', 0):.6f}",
            "model_away": f"{mp.get('AWAY', 0):.6f}",
            "market_home": f"{mk.get('HOME', 0):.6f}",
            "market_draw": f"{mk.get('DRAW', 0):.6f}",
            "market_away": f"{mk.get('AWAY', 0):.6f}",
            "selected_model_probability": f"{value.model_probability:.8f}" if value else "",
            "selected_market_probability": f"{value.market_probability:.8f}" if value else "",
            "edge": f"{value.edge:.6f}" if value else "",
            "probability_edge": f"{value.probability_edge:.6f}" if value else "",
            "expected_value": f"{value.expected_value:.6f}" if value else "",
            "odds": f"{value.odds:.3f}" if value and value.odds else "",
            "bookmaker": value.bookmaker or "" if value else "",
            "market": value.market if value else "",
            "fair_odds": f"{value.fair_odds:.3f}" if value and value.fair_odds else "",
            "raw_kelly_fraction": f"{p.raw_kelly_fraction:.6f}",
            "fractional_kelly": f"{p.fractional_kelly:.6f}",
            "stake_units": f"{p.stake_units:.3f}",
            "stake_reason": p.stake_reason,
            "post_international_break": str(p.post_international_break),
            "selected_attr_elo": f"{selected_attr.get('elo_adjustment', 0):.6f}" if selected_attr else "",
            "selected_attr_xg": f"{selected_attr.get('xg_form_adjustment', 0):.6f}" if selected_attr else "",
            "selected_attr_poisson": f"{selected_attr.get('poisson_adjustment', 0):.6f}" if selected_attr else "",
            "selected_attr_injury": f"{selected_attr.get('injury_impact', 0):.6f}" if selected_attr else "",
            "selected_attr_fatigue": f"{selected_attr.get('fatigue_impact', 0):.6f}" if selected_attr else "",
            "selected_attr_motivation": f"{selected_attr.get('motivation_impact', 0):.6f}" if selected_attr else "",
            "selected_attr_calibration": f"{selected_attr.get('calibration_adjustment', 0):.6f}" if selected_attr else "",
            "sharp_movement_selection": f"{float(sharp_move):.6f}" if sharp_move != "" else "",
        }
