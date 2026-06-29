import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from football_agent.schemas import Fixture, PickDecision, ValueDecision
from football_agent.storage.notification_state import NotificationState
from football_agent.reports.telegram import TelegramReporter
from football_agent.reports.live_sheet_export import LiveSheetExporter
from football_agent.utils_time import minutes_until


class V2507PremiumTelegramOpsTests(unittest.TestCase):
    def _pick(self, status="VALUE_PICK", selection="HOME", lineup=False):
        fixture = Fixture("fx1", "eredivisie", "Eredivisie", "PSV", "Feyenoord", "2099-09-14T14:00:00Z")
        value = ValueDecision(
            selection=selection,
            model_probability=0.58,
            market_probability=0.50,
            odds=1.95,
            edge=0.131,
            fair_odds=1.72,
            status="VALUE_CANDIDATE",
            reason="test",
            bookmaker="bet365",
            probability_edge=0.08,
            expected_value=0.131,
            market="OVER_UNDER_2_5",
        )
        return PickDecision(
            fixture=fixture,
            status=status,
            advice="Over 2.5 goals",
            selection=selection if status != "NO_BET" else None,
            value_decision=value,
            confidence=8.0,
            data_quality=9.0,
            risk_score=2.0,
            explanation_facts={"model_probabilities": {"HOME": 0.58, "DRAW": 0.23, "AWAY": 0.19}, "value": value.__dict__},
            time_window="PREMATCH",
            lineup_confirmed=lineup,
            uncertainty_score=2.0,
            stake_units=1.5,
            fractional_kelly=0.015,
            stake_reason="test stake",
        )

    def test_notification_state_sends_once_and_detects_withdrawal(self):
        with tempfile.TemporaryDirectory() as d:
            state = NotificationState(Path(d) / "state.json")
            p = self._pick()
            first = state.classify_pick(p)
            self.assertTrue(first.should_send)
            self.assertFalse(first.disable_notification)
            state.mark_pick(p, sent=True)
            second = state.classify_pick(p)
            self.assertFalse(second.should_send)
            withdrawn = self._pick(status="WATCHLIST")
            w = state.classify_pick(withdrawn)
            self.assertTrue(w.should_send)
            self.assertFalse(w.disable_notification)
            state.save()
            saved = json.loads((Path(d) / "state.json").read_text())
            self.assertIn("picks", saved)

    def test_telegram_send_can_be_silent_or_loud(self):
        reporter = TelegramReporter(token="token", chat_id="chat", enabled=True)
        with patch("football_agent.reports.telegram.requests.post") as post:
            post.return_value.raise_for_status.return_value = None
            reporter.send("hello", disable_notification=True)
            payload = post.call_args.kwargs["json"]
            self.assertTrue(payload["disable_notification"])
            reporter.send("alert", disable_notification=False)
            payload = post.call_args.kwargs["json"]
            self.assertFalse(payload["disable_notification"])

    def test_value_pick_alert_contains_units_and_min_odds(self):
        msg = TelegramReporter(enabled=False).build_value_pick_alert(self._pick())
        self.assertIn("VALUE PICK", msg)
        self.assertIn("Stake", msg)
        self.assertIn("Min. odds", msg)
        self.assertIn("T-55", msg)

    def test_live_sheet_export_writes_transparent_csv(self):
        with tempfile.TemporaryDirectory() as d:
            path = LiveSheetExporter(Path(d) / "live.csv").write([self._pick()])
            text = path.read_text()
            self.assertIn("stake_units", text)
            self.assertIn("PSV vs Feyenoord", text)

    def test_minutes_until_handles_future_fixture(self):
        mins = minutes_until("2099-01-01T00:00:00Z")
        self.assertIsNotNone(mins)
        self.assertGreater(mins, 0)


if __name__ == "__main__":
    unittest.main()
