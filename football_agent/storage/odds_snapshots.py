from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable
from football_agent.schemas import Fixture, OddsSnapshot


class OddsSnapshotStore:
    FIELDNAMES = ["fixture_id", "competition_key", "home_team", "away_team", "bookmaker", "profile", "market", "selection", "odds", "timestamp_utc", "opening_odds", "closing_odds"]

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, fixture: Fixture, odds: Iterable[OddsSnapshot]) -> None:
        exists = self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            if not exists:
                writer.writeheader()
            for o in odds:
                writer.writerow({
                    "fixture_id": fixture.id,
                    "competition_key": fixture.competition_key,
                    "home_team": fixture.home_team,
                    "away_team": fixture.away_team,
                    "bookmaker": o.bookmaker,
                    "profile": o.profile,
                    "market": o.market,
                    "selection": o.selection,
                    "odds": o.odds,
                    "timestamp_utc": o.timestamp_utc,
                    "opening_odds": o.opening_odds or "",
                    "closing_odds": o.closing_odds or "",
                })
