from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from football_agent.schemas import Fixture, OddsSnapshot, utc_now_iso
from football_agent.storage.model_versions import MODEL_VERSION, CONFIG_VERSION, FEATURE_SET_VERSION, CALIBRATION_VERSION


class DataSnapshotStore:
    """Persist the exact data context used for every prediction.

    A professional model needs auditability: when a pick is evaluated later, we
    must know which odds, standings, lineups, model version and timestamps were
    visible at decision time.
    """

    INDEX_FIELDNAMES = [
        "snapshot_id", "created_at_utc", "fixture_id", "competition_key", "home_team", "away_team",
        "kickoff_utc", "time_window", "odds_count", "lineup_confirmed", "market_cleansing_failed",
        "model_version", "config_version", "feature_set_version", "calibration_version", "path",
    ]

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.snapshot_dir = self.base_dir / "data_snapshots"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.base_dir / "data_snapshots_index.csv"

    def create(
        self,
        *,
        fixture: Fixture,
        odds: Iterable[OddsSnapshot],
        market_probabilities: Optional[Dict[str, float]],
        standings: Any = None,
        lineups: Any = None,
        time_window: str = "UNKNOWN",
        market_cleansing_failed: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        odds_list = list(odds or [])
        created_at = utc_now_iso()
        payload: Dict[str, Any] = {
            "created_at_utc": created_at,
            "fixture": asdict(fixture),
            "odds": [asdict(o) for o in odds_list],
            "market_probabilities": market_probabilities or {},
            "standings": self._safe_json(standings),
            "lineups": self._safe_json(lineups),
            "lineup_confirmed": bool(lineups),
            "time_window": time_window,
            "market_cleansing_failed": market_cleansing_failed,
            "model_version": MODEL_VERSION,
            "config_version": CONFIG_VERSION,
            "feature_set_version": FEATURE_SET_VERSION,
            "calibration_version": CALIBRATION_VERSION,
            "extra": extra or {},
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        snapshot_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        payload["snapshot_id"] = snapshot_id
        path = self.snapshot_dir / f"{snapshot_id}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        self._append_index(payload, path, len(odds_list))
        return snapshot_id

    def _append_index(self, payload: Dict[str, Any], path: Path, odds_count: int) -> None:
        exists = self.index_path.exists()
        fixture = payload["fixture"]
        with self.index_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.INDEX_FIELDNAMES)
            if not exists:
                writer.writeheader()
            writer.writerow({
                "snapshot_id": payload["snapshot_id"],
                "created_at_utc": payload["created_at_utc"],
                "fixture_id": fixture.get("id", ""),
                "competition_key": fixture.get("competition_key", ""),
                "home_team": fixture.get("home_team", ""),
                "away_team": fixture.get("away_team", ""),
                "kickoff_utc": fixture.get("kickoff_utc", ""),
                "time_window": payload.get("time_window", "UNKNOWN"),
                "odds_count": odds_count,
                "lineup_confirmed": payload.get("lineup_confirmed", False),
                "market_cleansing_failed": payload.get("market_cleansing_failed", False),
                "model_version": payload.get("model_version", ""),
                "config_version": payload.get("config_version", ""),
                "feature_set_version": payload.get("feature_set_version", ""),
                "calibration_version": payload.get("calibration_version", ""),
                "path": str(path),
            })

    def _safe_json(self, obj: Any) -> Any:
        try:
            json.dumps(obj, default=str)
            return obj
        except TypeError:
            return str(obj)
