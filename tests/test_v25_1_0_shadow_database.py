import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from football_agent.database.connection import DatabaseSettings, SupabaseRestClient
from football_agent.database.repository import (
    deterministic_pick_id,
    pick_identity,
    pick_identity_from_values,
)
from football_agent.database.shadow_writer import ShadowDatabaseWriter
from football_agent.schemas import Fixture, OddsSnapshot, PickDecision, ValueDecision


class RecordingRepository:
    def __init__(self, fail_operation=None):
        self.calls = []
        self.fail_operation = fail_operation

    def _record(self, name, *args, **kwargs):
        if self.fail_operation == name:
            raise RuntimeError(f"forced failure: {name}")
        self.calls.append((name, args, kwargs))

    def start_workflow_run(self, *args, **kwargs):
        self._record("start_workflow_run", *args, **kwargs)

    def finish_workflow_run(self, *args, **kwargs):
        self._record("finish_workflow_run", *args, **kwargs)

    def upsert_fixtures(self, fixtures):
        rows = list(fixtures)
        self._record("upsert_fixtures", rows)
        return len(rows)

    def upsert_odds_snapshots(self, observations):
        rows = list(observations)
        self._record("upsert_odds_snapshots", rows)
        return sum(len(odds) for _, odds in rows)

    def upsert_picks(self, picks):
        rows = list(picks)
        self._record("upsert_picks", rows)
        return len(rows)

    def upsert_observation_events(self, picks, run_id):
        rows = list(picks)
        self._record("upsert_observation_events", rows, run_id)
        return len(rows)

    def upsert_notification_state(self, *args, **kwargs):
        self._record("upsert_notification_state", *args, **kwargs)


class TestV2510ShadowDatabase(unittest.TestCase):
    def fixture(self):
        return Fixture(
            id="fx-100",
            competition_key="eredivisie",
            competition_name="Eredivisie",
            home_team="PSV",
            away_team="Feyenoord",
            kickoff_utc="2099-09-14T14:00:00Z",
        )

    def pick(self):
        value = ValueDecision(
            selection="OVER_2_5",
            model_probability=0.60,
            market_probability=0.53,
            odds=1.95,
            edge=0.17,
            fair_odds=1.67,
            status="VALUE_CANDIDATE",
            reason="test",
            bookmaker="Bet365",
            expected_value=0.17,
            market="OVER_UNDER_2_5",
        )
        return PickDecision(
            fixture=self.fixture(),
            status="VALUE_PICK",
            advice="Over 2.5",
            selection="OVER_2_5",
            value_decision=value,
            confidence=8.0,
            data_quality=8.5,
            risk_score=2.0,
            explanation_facts={},
            model_version="V25.1.0-test",
            stake_units=1.0,
        )

    def active_settings(self, fail_open=True):
        return DatabaseSettings(
            enabled=True,
            shadow_mode=True,
            fail_open=fail_open,
            supabase_url="https://example.supabase.co",
            secret_key="test-secret-not-real",
        )

    def test_pick_identity_is_stable_when_odds_or_bookmaker_change(self):
        first = self.pick()
        identity_1 = pick_identity(first)
        first.value_decision.odds = 2.05
        first.value_decision.bookmaker = "Unibet"
        identity_2 = pick_identity(first)
        self.assertEqual(identity_1, identity_2)
        self.assertEqual(deterministic_pick_id(identity_1), deterministic_pick_id(identity_2))
        self.assertEqual(
            identity_1,
            pick_identity_from_values("fx-100", "OVER_UNDER_2_5", "OVER_2_5", "V25.1.0-test"),
        )

    def test_shadow_writer_dual_writes_without_replacing_local_pipeline(self):
        repository = RecordingRepository()
        with TemporaryDirectory() as td:
            writer = ShadowDatabaseWriter(td, "daily", settings=self.active_settings(), repository=repository)
            writer.begin({"test": True})
            odds = [OddsSnapshot("Bet365", "OVER_UNDER_2_5", "OVER_2_5", 1.95, "2099-09-14T10:00:00Z")]
            pick = self.pick()
            writer.record_observations([(pick.fixture, odds)], [pick])
            writer.record_notification(pick, action="new_value_pick", sent=True)
            writer.finish({"scanned": 1, "value_picks": 1})

            call_names = [call[0] for call in repository.calls]
            self.assertIn("start_workflow_run", call_names)
            self.assertIn("upsert_fixtures", call_names)
            self.assertIn("upsert_odds_snapshots", call_names)
            self.assertIn("upsert_picks", call_names)
            self.assertIn("upsert_observation_events", call_names)
            self.assertIn("upsert_notification_state", call_names)
            self.assertIn("finish_workflow_run", call_names)

            report = json.loads((Path(td) / "shadow_database_report.json").read_text())
            self.assertTrue(report["active"])
            self.assertEqual(report["pick_rows"], 1)
            self.assertEqual(report["notification_rows"], 1)
            self.assertEqual(report["failures"], [])

    def test_shadow_database_is_fail_open(self):
        repository = RecordingRepository(fail_operation="upsert_picks")
        with TemporaryDirectory() as td:
            writer = ShadowDatabaseWriter(td, "daily", settings=self.active_settings(fail_open=True), repository=repository)
            writer.begin()
            pick = self.pick()
            # Must not raise, because the existing CSV/Telegram pipeline remains authoritative.
            writer.record_observations([(pick.fixture, [])], [pick])
            writer.finish({"scanned": 1})
            report = json.loads((Path(td) / "shadow_database_report.json").read_text())
            self.assertTrue(report["failures"])
            self.assertTrue((Path(td) / "shadow_database_failures.jsonl").exists())

    def test_database_settings_do_not_expose_secret(self):
        with patch.dict(os.environ, {
            "DATABASE_ENABLED": "true",
            "DATABASE_SHADOW_MODE": "true",
            "DATABASE_FAIL_OPEN": "true",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SECRET_KEY": "very-secret",
        }, clear=False):
            settings = DatabaseSettings.from_env()
            summary = settings.safe_summary()
            self.assertTrue(settings.active)
            self.assertNotIn("very-secret", json.dumps(summary))
            self.assertNotIn("secret_key", summary)


    def test_unsent_value_pick_is_retried_instead_of_suppressed(self):
        from football_agent.storage.notification_state import NotificationState
        with TemporaryDirectory() as td:
            state = NotificationState(Path(td) / "notification_state.json")
            pick = self.pick()
            state.mark_pick(pick, sent=False)
            decision = state.classify_pick(pick)
            self.assertTrue(decision.should_send)
            self.assertEqual(decision.action, "new_value_pick")


    def test_shadow_compare_since_filters_older_local_rows(self):
        import csv
        from football_agent.scripts.compare_shadow_state import _local_pick_identities
        with TemporaryDirectory() as td:
            path = Path(td) / "prediction_log.csv"
            fieldnames = ["created_at_utc", "fixture_id", "market", "selection", "model_version"]
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow({
                    "created_at_utc": "2026-06-20T10:00:00Z",
                    "fixture_id": "old", "market": "1X2", "selection": "HOME", "model_version": "v",
                })
                writer.writerow({
                    "created_at_utc": "2026-06-21T10:00:00Z",
                    "fixture_id": "new", "market": "1X2", "selection": "HOME", "model_version": "v",
                })
            identities, _ = _local_pick_identities(path, "2026-06-21T00:00:00Z")
            self.assertEqual(len(identities), 1)
            self.assertTrue(identities[0].startswith("new|"))


    def test_supabase_select_paginates_and_upsert_batches(self):
        class FakeResponse:
            def __init__(self, payload, status_code=200):
                self._payload = payload
                self.status_code = status_code
                self.headers = {}
            def json(self):
                return self._payload
            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(self.status_code)

        class FakeSession:
            def __init__(self):
                self.calls = []
            def request(self, **kwargs):
                self.calls.append(kwargs)
                if kwargs["method"] == "GET":
                    offset = int(kwargs["params"].get("offset", 0))
                    limit = int(kwargs["params"].get("limit", 1000))
                    total = 1205
                    payload = [{"identity_key": str(i)} for i in range(offset, min(offset + limit, total))]
                    return FakeResponse(payload)
                return FakeResponse([])

        settings = DatabaseSettings(
            enabled=True, shadow_mode=True, fail_open=True,
            supabase_url="https://example.supabase.co", secret_key="sb_secret_example",
            batch_size=2,
        )
        session = FakeSession()
        client = SupabaseRestClient(settings, session=session)
        rows = client.select("picks", columns="identity_key", limit=1205)
        self.assertEqual(len(rows), 1205)
        get_calls = [c for c in session.calls if c["method"] == "GET"]
        self.assertEqual(len(get_calls), 2)

        client.upsert("fixtures", [{"fixture_id": str(i)} for i in range(5)], on_conflict="fixture_id")
        post_calls = [c for c in session.calls if c["method"] == "POST"]
        self.assertEqual([len(c["json"]) for c in post_calls], [2, 2, 1])

    def test_supabase_secret_key_is_not_sent_as_jwt_bearer(self):
        settings = DatabaseSettings(
            enabled=True, shadow_mode=True, fail_open=True,
            supabase_url="https://example.supabase.co", secret_key="sb_secret_example",
        )
        headers = SupabaseRestClient(settings)._headers()
        self.assertEqual(headers["apikey"], "sb_secret_example")
        self.assertNotIn("Authorization", headers)

        legacy = DatabaseSettings(
            enabled=True, shadow_mode=True, fail_open=True,
            supabase_url="https://example.supabase.co", secret_key="eyJlegacyjwt",
        )
        legacy_headers = SupabaseRestClient(legacy)._headers()
        self.assertEqual(legacy_headers["Authorization"], "Bearer eyJlegacyjwt")


if __name__ == "__main__":
    unittest.main()
