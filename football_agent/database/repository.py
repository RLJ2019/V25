from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence

from football_agent.database.connection import SupabaseRestClient
from football_agent.schemas import Fixture, OddsSnapshot, PickDecision
from football_agent.storage.notification_state import NotificationState


PICK_NAMESPACE = uuid.UUID("a44ec13f-e40a-46fa-acfc-55ff92e629a7")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_odds_snapshot_timestamp_for_key(timestamp_utc: str) -> str:
    """Normalize provider odds timestamps to minute precision for idempotent snapshot keys.

    API-Football can return timestamps with second-level differences for the same
    bookmaker/market/selection/odds observation. For database idempotency we keep
    the raw provider timestamp in `snapshot_timestamp_utc`, but hash the minute-
    normalized timestamp into `snapshot_key`. Odds changes still create a new key
    because the odds value remains part of the hash.
    """
    value = str(timestamp_utc or "").strip()
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        # Stable fallback for ISO-like provider strings that are not fully parseable.
        # Keeps YYYY-MM-DDTHH:MM when present instead of hashing volatile seconds.
        return value[:16] if len(value) >= 16 and "T" in value[:16] else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    normalized = parsed.astimezone(timezone.utc).replace(second=0, microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def odds_snapshot_identity_key(fixture_id: str, snapshot: OddsSnapshot) -> str:
    normalized_timestamp = normalize_odds_snapshot_timestamp_for_key(snapshot.timestamp_utc)
    return sha256_text("|".join([
        str(fixture_id),
        snapshot.bookmaker,
        snapshot.market,
        snapshot.selection,
        normalized_timestamp,
        f"{snapshot.odds:.6f}",
    ]))


def pick_identity_from_values(
    fixture_id: str,
    market: str,
    selection: str,
    model_version: str,
) -> str:
    # Bookmaker and odds are intentionally excluded: a line-up update or better soft-book
    # price belongs to the same proposition and should become an AMENDED event, not a new pick.
    return "|".join([
        str(fixture_id),
        (market or "1X2").upper(),
        (selection or "NONE").upper(),
        model_version or "unknown",
    ])


def pick_identity(pick: PickDecision) -> str:
    market = pick.value_decision.market if pick.value_decision else "1X2"
    return pick_identity_from_values(pick.fixture.id, market, pick.selection or "NONE", pick.model_version)


def deterministic_pick_id(identity_key: str) -> str:
    return str(uuid.uuid5(PICK_NAMESPACE, identity_key))


def workflow_run_id() -> str:
    repository = os.getenv("GITHUB_REPOSITORY", "local")
    workflow = os.getenv("GITHUB_WORKFLOW", "local")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
    if run_id:
        return f"gha:{repository}:{workflow}:{run_id}:{attempt}"
    return f"local:{uuid.uuid4()}"


class DatabaseRepository:
    def __init__(self, client: SupabaseRestClient):
        self.client = client

    def upsert_fixtures(self, fixtures: Iterable[Fixture]) -> int:
        rows = []
        for fixture in fixtures:
            rows.append({
                "fixture_id": str(fixture.id),
                "api_football_fixture_id": fixture.api_football_fixture_id,
                "football_data_match_id": fixture.football_data_match_id,
                "competition_key": fixture.competition_key,
                "competition_name": fixture.competition_name,
                "home_team": fixture.home_team,
                "away_team": fixture.away_team,
                "kickoff_utc": fixture.kickoff_utc,
                "status": fixture.status,
                "source": fixture.source,
                "home_score": fixture.home_score,
                "away_score": fixture.away_score,
                "updated_at": utc_now(),
            })
        self.client.upsert("fixtures", rows, on_conflict="fixture_id")
        return len(rows)

    def upsert_odds_snapshots(self, observations: Iterable[tuple[Fixture, Sequence[OddsSnapshot]]]) -> int:
        rows_by_key: Dict[str, Dict[str, Any]] = {}
        for fixture, odds in observations:
            for snapshot in odds:
                snapshot_key = odds_snapshot_identity_key(str(fixture.id), snapshot)
                rows_by_key[snapshot_key] = {
                    "snapshot_key": snapshot_key,
                    "fixture_id": str(fixture.id),
                    "bookmaker": snapshot.bookmaker,
                    "market": snapshot.market,
                    "selection": snapshot.selection,
                    "odds": snapshot.odds,
                    "profile": snapshot.profile,
                    "opening_odds": snapshot.opening_odds,
                    "provider_closing_odds": snapshot.closing_odds,
                    "snapshot_timestamp_utc": snapshot.timestamp_utc,
                    "is_closing_line": False,
                    "captured_at": utc_now(),
                }
        rows = list(rows_by_key.values())
        self.client.upsert("odds_snapshots", rows, on_conflict="snapshot_key")
        return len(rows)

    def upsert_picks(self, picks: Iterable[PickDecision]) -> int:
        rows = []
        for pick in picks:
            value = pick.value_decision
            identity_key = pick_identity(pick)
            rows.append({
                "pick_id": deterministic_pick_id(identity_key),
                "identity_key": identity_key,
                "fixture_id": str(pick.fixture.id),
                "competition_key": pick.fixture.competition_key,
                "competition_name": pick.fixture.competition_name,
                "market": value.market if value else "1X2",
                "selection": pick.selection or "NONE",
                "bookmaker": value.bookmaker if value else None,
                "status": pick.status,
                "advice": pick.advice,
                "entry_odds": value.odds if value else None,
                "fair_odds": value.fair_odds if value else None,
                "sharp_fair_odds": value.sharp_fair_odds if value else None,
                "min_acceptable_odds": value.min_acceptable_odds if value else None,
                "model_probability": value.model_probability if value else None,
                "market_probability": value.market_probability if value else None,
                "expected_value": value.expected_value if value else None,
                "probability_edge": value.probability_edge if value else None,
                "confidence": pick.confidence,
                "data_quality": pick.data_quality,
                "risk_score": pick.risk_score,
                "uncertainty_score": pick.uncertainty_score,
                "stake_units": pick.stake_units,
                "stake_reason": pick.stake_reason,
                "time_window": pick.time_window,
                "lineup_confirmed": pick.lineup_confirmed,
                "data_snapshot_id": pick.data_snapshot_id,
                "model_version": pick.model_version,
                "config_version": pick.config_version,
                "feature_set_version": pick.feature_set_version,
                "calibration_version": pick.calibration_version,
                "original_created_at": pick.created_at_utc,
                "last_seen_at": utc_now(),
            })
        self.client.upsert("picks", rows, on_conflict="identity_key")
        return len(rows)

    def upsert_observation_events(self, picks: Iterable[PickDecision], run_id: str) -> int:
        rows = []
        for pick in picks:
            identity_key = pick_identity(pick)
            signature = NotificationState.signature(pick)
            event_key = sha256_text(f"{identity_key}|OBSERVED|{signature}")
            rows.append({
                "event_key": event_key,
                "pick_id": deterministic_pick_id(identity_key),
                "event_type": "OBSERVED",
                "details": {
                    "status": pick.status,
                    "signature": signature,
                    "time_window": pick.time_window,
                    "lineup_confirmed": pick.lineup_confirmed,
                    "run_id": run_id,
                },
                "event_timestamp": utc_now(),
            })
        self.client.upsert("pick_events", rows, on_conflict="event_key")
        return len(rows)

    def upsert_notification_state(
        self,
        pick: PickDecision,
        *,
        action: str,
        sent: bool,
        run_id: str,
    ) -> None:
        value = pick.value_decision
        market = value.market if value else "1X2"
        identity_key = pick_identity(pick)
        signature = NotificationState.signature(pick)
        message_key = sha256_text(f"{identity_key}|{action}|{signature}")
        self.client.upsert("notification_state_shadow", [{
            "fixture_id": str(pick.fixture.id),
            "market": market,
            "selection": pick.selection or "NONE",
            "pick_id": deterministic_pick_id(identity_key),
            "status": pick.status,
            "signature": signature,
            "last_action": action,
            "message_key": message_key,
            "sent": bool(sent),
            "run_id": run_id,
            "last_updated_at": utc_now(),
        }], on_conflict="fixture_id,market,selection")

        if action != "no_alert":
            event_type = {
                "new_value_pick": "ALERT_SENT" if sent else "ALERT_ATTEMPTED",
                "upgraded_to_value_pick": "CONFIRMED" if sent else "ALERT_ATTEMPTED",
                "value_pick_changed": "AMENDED" if sent else "ALERT_ATTEMPTED",
                "value_pick_withdrawn": "WITHDRAWN" if sent else "ALERT_ATTEMPTED",
            }.get(action, "NOTIFICATION_EVENT")
            event_key = sha256_text(f"{identity_key}|{event_type}|{signature}")
            self.client.upsert("pick_events", [{
                "event_key": event_key,
                "pick_id": deterministic_pick_id(identity_key),
                "event_type": event_type,
                "details": {
                    "notification_action": action,
                    "sent": bool(sent),
                    "message_key": message_key,
                    "run_id": run_id,
                },
                "event_timestamp": utc_now(),
            }], on_conflict="event_key")

    def start_workflow_run(self, run_id: str, run_type: str, metadata: Mapping[str, Any]) -> None:
        self.client.upsert("workflow_runs", [{
            "run_id": run_id,
            "run_type": run_type,
            "source": "github_actions" if os.getenv("GITHUB_ACTIONS") == "true" else "local",
            "status": "RUNNING",
            "started_at": utc_now(),
            "metadata": dict(metadata),
        }], on_conflict="run_id")

    def finish_workflow_run(
        self,
        run_id: str,
        *,
        run_type: str,
        status: str,
        summary: Mapping[str, Any],
        error: str | None = None,
    ) -> None:
        # PostgREST upsert updates the existing row because run_id is the conflict key.
        self.client.upsert("workflow_runs", [{
            "run_id": run_id,
            "run_type": run_type,
            "status": status,
            "finished_at": utc_now(),
            "summary": dict(summary),
            "error": error,
        }], on_conflict="run_id")

    def fetch_picks(self, limit: int = 10000) -> list[dict[str, Any]]:
        return self.client.select(
            "picks",
            columns=(
                "pick_id,identity_key,fixture_id,market,selection,status,model_version,last_seen_at,"
                "entry_odds,model_probability,market_probability,expected_value,probability_edge,stake_units"
            ),
            limit=limit,
        )

    def fetch_notification_state(self, limit: int = 10000) -> list[dict[str, Any]]:
        return self.client.select(
            "notification_state_shadow",
            columns="fixture_id,market,selection,status,signature,sent,last_action,last_updated_at",
            limit=limit,
        )

    # V25.1.3 settlement pipeline read/write helpers. These are only used by
    # football_agent.scripts.run_settlement and do not alter daily pick generation.
    def fetch_unsettled_value_picks(self, limit: int = 1000) -> list[dict[str, Any]]:
        existing = {str(row.get("pick_id")) for row in self.client.select("settlements", columns="pick_id", limit=10000)}
        rows = self.client.select(
            "picks",
            columns=(
                "pick_id,identity_key,fixture_id,competition_key,competition_name,market,selection,bookmaker,status,"
                "entry_odds,model_probability,market_probability,stake_units,original_created_at,last_seen_at"
            ),
            filters={"status": "eq.VALUE_PICK"},
            limit=limit,
        )
        out: list[dict[str, Any]] = []
        for row in rows:
            if str(row.get("pick_id")) in existing:
                continue
            try:
                if float(row.get("stake_units") or 0) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
            out.append(row)
        return out

    def fetch_fixture_by_id(self, fixture_id: str) -> dict[str, Any] | None:
        rows = self.client.select(
            "fixtures",
            columns="fixture_id,api_football_fixture_id,competition_key,competition_name,home_team,away_team,kickoff_utc,status,source,home_score,away_score",
            filters={"fixture_id": f"eq.{fixture_id}"},
            limit=1,
        )
        return rows[0] if rows else None

    def fetch_closing_odds_bundle(self, fixture_id: str, market: str, selection: str, *, line: Any = None, limit: int = 1000) -> list[dict[str, Any]]:
        rows = self.client.select(
            "odds_snapshots",
            columns="snapshot_key,fixture_id,bookmaker,market,selection,odds,profile,snapshot_timestamp_utc,captured_at",
            filters={"fixture_id": f"eq.{fixture_id}", "market": f"eq.{market}"},
            limit=limit,
        )
        # PostgREST ordering is intentionally not required here; CLV selects complete
        # bundles and the repository keeps enough rows for a fixture-level close.
        return rows

    def upsert_settlements(self, rows: Iterable[Mapping[str, Any]]) -> int:
        payload = [dict(row) for row in rows]
        self.client.upsert("settlements", payload, on_conflict="pick_id")
        return len(payload)
