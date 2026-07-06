from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from football_agent.schemas import PickDecision


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class NotificationDecision:
    action: str
    should_send: bool
    disable_notification: bool
    reason: str


class NotificationState:
    """Persistent Telegram notification de-duplication and status-transition tracker.

    The agent can run many times per day. This class prevents a premium Telegram group
    from receiving the same VALUE_PICK repeatedly while still sending important status
    transitions such as a watchlist pick becoming a confirmed value pick or a pick being
    withdrawn after line-up/sharp-market changes.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state: Dict = {"picks": {}, "heartbeats": {}}
        if self.path.exists():
            try:
                self.state.update(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                # Corrupt state should never crash the agent; start clean and overwrite.
                self.state = {"picks": {}, "heartbeats": {}}

    @staticmethod
    def pick_key(pick: PickDecision) -> str:
        selection = pick.selection or "NONE"
        return f"{pick.fixture.id}|{selection}"

    @staticmethod
    def signature(pick: PickDecision) -> str:
        value = pick.value_decision
        expected_value = value.expected_value if value else 0.0
        odds = value.odds if value and value.odds is not None else 0.0
        bookmaker = value.bookmaker if value else ""
        market = value.market if value else ""
        return "|".join([
            pick.status,
            pick.selection or "NONE",
            market,
            f"{expected_value:.5f}",
            f"{odds:.4f}",
            bookmaker or "",
            f"{pick.stake_units:.3f}",
            str(bool(pick.lineup_confirmed)),
            pick.time_window,
        ])

    def classify_pick(self, pick: PickDecision) -> NotificationDecision:
        key = self.pick_key(pick)
        previous: Optional[Dict] = self.state.get("picks", {}).get(key)
        previous_status = previous.get("status") if previous else None
        previous_signature = previous.get("signature") if previous else None
        previous_sent = bool(previous.get("sent")) if previous else False
        current_signature = self.signature(pick)

        if pick.status == "VALUE_PICK":
            if previous is None:
                return NotificationDecision("new_value_pick", True, False, "Nieuwe value pick.")
            if previous_status != "VALUE_PICK":
                return NotificationDecision("upgraded_to_value_pick", True, False, f"Status ging van {previous_status} naar VALUE_PICK.")
            if previous_signature != current_signature:
                return NotificationDecision("value_pick_changed", True, False, "Bestaande value pick is inhoudelijk gewijzigd.")
            if not previous_sent:
                return NotificationDecision("new_value_pick", True, False, "Eerdere verzending was niet succesvol; opnieuw aanbieden.")
            return NotificationDecision("duplicate_value_pick", False, False, "Value pick is al verstuurd.")

        if previous_status == "VALUE_PICK" and previous_sent and pick.status != "VALUE_PICK":
            # Premium UX: a withdrawal is as urgent as the original value-pick alert.
            # Members may already have acted on the pick, so this must be loud.
            return NotificationDecision("value_pick_withdrawn", True, False, f"Value pick ingetrokken naar {pick.status}.")

        return NotificationDecision("no_alert", False, True, "Geen Telegram alert nodig.")

    def mark_pick(self, pick: PickDecision, sent: bool = False) -> None:
        key = self.pick_key(pick)
        self.state.setdefault("picks", {})[key] = {
            "status": pick.status,
            "selection": pick.selection or "",
            "fixture_id": pick.fixture.id,
            "matchup": pick.fixture.matchup,
            "kickoff_utc": pick.fixture.kickoff_utc,
            "signature": self.signature(pick),
            "sent": bool(sent),
            "updated_at_utc": _utc_now(),
        }

    def active_fixture_ids(self, statuses: set[str] | None = None) -> set[str]:
        statuses = statuses or {"WATCHLIST", "VALUE_PICK"}
        ids: set[str] = set()
        for item in self.state.get("picks", {}).values():
            if item.get("status") in statuses and item.get("fixture_id"):
                ids.add(str(item["fixture_id"]))
        return ids

    def should_send_heartbeat(self, key: str) -> bool:
        return key not in self.state.setdefault("heartbeats", {})

    def mark_heartbeat(self, key: str) -> None:
        self.state.setdefault("heartbeats", {})[key] = {"sent_at_utc": _utc_now()}

    def save(self) -> None:
        # Atomic local write. Together with a shared GitHub Actions concurrency group
        # this prevents partially-written/corrupt notification state files. For a
        # paid production service, this local backend should be replaced by a central
        # DB/object-store backend with locking.
        payload = json.dumps(self.state, indent=2, sort_keys=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self.path)
