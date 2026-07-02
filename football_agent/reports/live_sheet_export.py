from __future__ import annotations

import csv
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Iterable, List, Dict

import requests

from football_agent.schemas import PickDecision


class LiveSheetExporter:
    """Writes a transparent CSV that can be mirrored into a read-only Google Sheet.

    V25.0.9: webhook sync is idempotent and retried. The Sheet is still a mirror,
    never the source of truth. If the webhook fails, prediction_log.csv/live CSV can
    be used to resync later.
    """

    FIELDNAMES = [
        "created_at_utc", "status", "competition", "match", "kickoff_utc", "market",
        "selection", "odds", "min_acceptable_odds", "sharp_fair_odds", "baseline_source",
        "bookmaker", "expected_value", "probability_edge", "confidence", "data_quality",
        "uncertainty", "stake_units", "stake_reason", "time_window", "lineup_confirmed",
        "data_snapshot_id", "model_version",
    ]

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.failure_log_path = self.path.parent / "live_sheet_webhook_failures.jsonl"

    def rows(self, picks: Iterable[PickDecision]) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for p in picks:
            value = p.value_decision
            rows.append({
                "created_at_utc": p.created_at_utc,
                "status": p.status,
                "competition": p.fixture.competition_name,
                "match": p.fixture.matchup,
                "kickoff_utc": p.fixture.kickoff_utc,
                "market": value.market if value else "",
                "selection": p.selection or "",
                "odds": f"{value.odds:.3f}" if value and value.odds else "",
                "min_acceptable_odds": f"{value.min_acceptable_odds:.3f}" if value and value.min_acceptable_odds else "",
                "sharp_fair_odds": f"{value.sharp_fair_odds:.3f}" if value and value.sharp_fair_odds else "",
                "baseline_source": value.baseline_source if value else "",
                "bookmaker": value.bookmaker or "" if value else "",
                "expected_value": f"{value.expected_value:.6f}" if value else "",
                "probability_edge": f"{value.probability_edge:.6f}" if value else "",
                "confidence": f"{p.confidence:.2f}",
                "data_quality": f"{p.data_quality:.2f}",
                "uncertainty": f"{p.uncertainty_score:.2f}",
                "stake_units": f"{p.stake_units:.2f}",
                "stake_reason": p.stake_reason or "",
                "time_window": p.time_window,
                "lineup_confirmed": str(p.lineup_confirmed),
                "data_snapshot_id": p.data_snapshot_id or "",
                "model_version": p.model_version,
            })
        return rows

    def write(self, picks: Iterable[PickDecision]) -> Path:
        rows = self.rows(picks)
        with self.path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        return self.path

    def _idempotency_key(self, rows: List[Dict[str, str]]) -> str:
        raw = json.dumps(rows, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _log_failure(self, payload: Dict, error: str) -> None:
        item = {"error": error, "payload_hash": payload.get("idempotency_key"), "rows": len(payload.get("rows", []))}
        with self.failure_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    def push_webhook(self, picks: Iterable[PickDecision]) -> bool:
        """Optional Google Sheet bridge via Apps Script webhook.

        GOOGLE_SHEET_WEBHOOK_URL should accept JSON and use idempotency_key to upsert,
        not append blindly. We retry transient failures and log failed syncs for later
        reconciliation. The internal CSV/log remains the source of truth.
        """
        url = os.getenv("GOOGLE_SHEET_WEBHOOK_URL", "").strip()
        if not url:
            return False
        rows = self.rows(picks)
        payload = {"rows": rows, "idempotency_key": self._idempotency_key(rows), "schema_version": "v25.0.9"}
        attempts = int(os.getenv("LIVE_SHEET_WEBHOOK_RETRIES", "3"))
        for attempt in range(1, max(1, attempts) + 1):
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers={"Idempotency-Key": payload["idempotency_key"]},
                    timeout=30,
                )
                resp.raise_for_status()
                return True
            except Exception as exc:
                if attempt >= attempts:
                    print(f"Live Sheet webhook faalde definitief: {exc}")
                    self._log_failure(payload, str(exc))
                    return False
                time.sleep(min(2 ** attempt, 10))
        return False
