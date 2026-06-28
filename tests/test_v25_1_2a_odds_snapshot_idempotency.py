from __future__ import annotations

import unittest

from football_agent.database.repository import (
    DatabaseRepository,
    normalize_odds_snapshot_timestamp_for_key,
    odds_snapshot_identity_key,
)
from football_agent.schemas import Fixture, OddsSnapshot


class RecordingClient:
    def __init__(self):
        self.calls = []

    def upsert(self, table, rows, on_conflict=None):
        self.calls.append({
            "table": table,
            "rows": list(rows),
            "on_conflict": on_conflict,
        })


class TestV2512aOddsSnapshotIdempotency(unittest.TestCase):
    def fixture(self):
        return Fixture(
            id="fx-2512a",
            competition_key="eredivisie",
            competition_name="Eredivisie",
            home_team="PSV",
            away_team="Ajax",
            kickoff_utc="2099-09-14T14:00:00Z",
        )

    def snapshot(self, timestamp: str, odds: float = 2.05):
        return OddsSnapshot(
            bookmaker="bet365",
            market="1X2",
            selection="HOME",
            odds=odds,
            timestamp_utc=timestamp,
            profile="soft",
        )

    def test_timestamp_normalization_uses_utc_minute_precision(self):
        self.assertEqual(
            normalize_odds_snapshot_timestamp_for_key("2026-06-28T12:34:56Z"),
            "2026-06-28T12:34:00Z",
        )
        self.assertEqual(
            normalize_odds_snapshot_timestamp_for_key("2026-06-28T14:34:56+02:00"),
            "2026-06-28T12:34:00Z",
        )

    def test_same_minute_same_odds_produces_same_snapshot_key(self):
        first = self.snapshot("2026-06-28T12:34:01Z", odds=2.05)
        second = self.snapshot("2026-06-28T12:34:59Z", odds=2.05)

        self.assertEqual(
            odds_snapshot_identity_key("fx-2512a", first),
            odds_snapshot_identity_key("fx-2512a", second),
        )

    def test_different_minute_or_odds_produces_distinct_snapshot_key(self):
        base = self.snapshot("2026-06-28T12:34:01Z", odds=2.05)
        next_minute = self.snapshot("2026-06-28T12:35:00Z", odds=2.05)
        odds_move = self.snapshot("2026-06-28T12:34:30Z", odds=2.06)

        self.assertNotEqual(
            odds_snapshot_identity_key("fx-2512a", base),
            odds_snapshot_identity_key("fx-2512a", next_minute),
        )
        self.assertNotEqual(
            odds_snapshot_identity_key("fx-2512a", base),
            odds_snapshot_identity_key("fx-2512a", odds_move),
        )

    def test_repository_deduplicates_same_minute_rows_before_upsert(self):
        client = RecordingClient()
        repository = DatabaseRepository(client)
        fixture = self.fixture()
        odds = [
            self.snapshot("2026-06-28T12:34:01Z", odds=2.05),
            self.snapshot("2026-06-28T12:34:59Z", odds=2.05),
        ]

        written = repository.upsert_odds_snapshots([(fixture, odds)])

        self.assertEqual(written, 1)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["table"], "odds_snapshots")
        self.assertEqual(client.calls[0]["on_conflict"], "snapshot_key")
        self.assertEqual(len(client.calls[0]["rows"]), 1)

    def test_repository_keeps_true_odds_moves_within_same_minute(self):
        client = RecordingClient()
        repository = DatabaseRepository(client)
        fixture = self.fixture()
        odds = [
            self.snapshot("2026-06-28T12:34:01Z", odds=2.05),
            self.snapshot("2026-06-28T12:34:59Z", odds=2.06),
        ]

        written = repository.upsert_odds_snapshots([(fixture, odds)])

        self.assertEqual(written, 2)
        self.assertEqual(len(client.calls[0]["rows"]), 2)


if __name__ == "__main__":
    unittest.main()
