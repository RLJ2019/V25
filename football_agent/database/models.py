from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class DatabaseHealth:
    enabled: bool
    configured: bool
    reachable: bool
    backend: str
    message: str


@dataclass
class ShadowWriteReport:
    run_id: str
    run_type: str
    enabled: bool
    shadow_mode: bool
    started_at_utc: str
    completed_at_utc: str | None = None
    fixture_rows: int = 0
    odds_rows: int = 0
    pick_rows: int = 0
    event_rows: int = 0
    notification_rows: int = 0
    failures: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    odds_metrics: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures
