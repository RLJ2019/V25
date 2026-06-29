from __future__ import annotations

import atexit
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from football_agent.database.connection import DatabaseSettings, SupabaseRestClient
from football_agent.database.models import ShadowWriteReport
from football_agent.database.repository import DatabaseRepository, utc_now, workflow_run_id
from football_agent.schemas import Fixture, OddsSnapshot, PickDecision


class ShadowDatabaseWriter:
    """Fail-open dual-writer used during V25.1.0 Phase 1.

    The existing CSV/JSON and Telegram pipeline stays authoritative. Database writes
    are mirrored in parallel and any failure is logged locally without interrupting
    predictions, alerts, or artifacts when DATABASE_FAIL_OPEN=true.
    """

    def __init__(
        self,
        output_dir: str | Path,
        run_type: str,
        *,
        settings: DatabaseSettings | None = None,
        repository: DatabaseRepository | None = None,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.settings = settings or DatabaseSettings.from_env()
        self.run_id = workflow_run_id()
        self.run_type = run_type
        if repository is None and self.settings.configured:
            repository = DatabaseRepository(SupabaseRestClient(self.settings))
        self.repository = repository
        self.report = ShadowWriteReport(
            run_id=self.run_id,
            run_type=run_type,
            enabled=self.settings.enabled,
            shadow_mode=self.settings.shadow_mode,
            started_at_utc=utc_now(),
        )
        self._finished = False
        self._atexit_registered = False

    @property
    def active(self) -> bool:
        return bool(self.settings.active and self.repository is not None)

    def _failure(self, operation: str, exc: Exception) -> None:
        item = {"operation": operation, "error": str(exc), "at_utc": utc_now()}
        self.report.failures.append(item)
        failure_path = self.output_dir / "shadow_database_failures.jsonl"
        with failure_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        print(f"Shadow database write failed [{operation}]: {exc}")
        if not self.settings.fail_open:
            raise exc

    def _safe(self, operation: str, function: Callable[[], Any], default: Any = None) -> Any:
        if not self.active:
            return default
        try:
            return function()
        except Exception as exc:  # deliberate fail-open boundary
            self._failure(operation, exc)
            return default

    def begin(self, metadata: dict[str, Any] | None = None) -> None:
        if not self._atexit_registered:
            atexit.register(self._finish_if_aborted)
            self._atexit_registered = True
        print(
            "Shadow database: enabled={enabled} configured={configured} active={active} "
            "mode={mode} fail_open={fail_open}".format(
                enabled=self.settings.enabled,
                configured=self.settings.configured,
                active=self.active,
                mode="shadow" if self.settings.shadow_mode else "source",
                fail_open=self.settings.fail_open,
            )
        )
        self._safe(
            "start_workflow_run",
            lambda: self.repository.start_workflow_run(
                self.run_id,
                self.run_type,
                {**self.settings.safe_summary(), **(metadata or {})},
            ),
        )
        self._write_report()


    def _finish_if_aborted(self) -> None:
        if self._finished:
            return
        try:
            self.finish(
                {"aborted_before_summary": True},
                status="FAILED",
                error="Process exited before the shadow workflow run completed.",
            )
        except Exception:
            # Never raise from an atexit handler. The local failure report written by
            # _safe/_failure remains available in the workflow artifact.
            pass

    def record_observations(
        self,
        observations: Iterable[tuple[Fixture, Sequence[OddsSnapshot]]],
        picks: Iterable[PickDecision],
    ) -> None:
        observations = list(observations)
        picks = list(picks)
        unique_fixtures = {str(fixture.id): fixture for fixture, _ in observations}
        self.report.fixture_rows += int(self._safe(
            "upsert_fixtures",
            lambda: self.repository.upsert_fixtures(unique_fixtures.values()),
            0,
        ) or 0)
        self.report.odds_rows += int(self._safe(
            "upsert_odds_snapshots",
            lambda: self.repository.upsert_odds_snapshots(observations),
            0,
        ) or 0)
        self.report.pick_rows += int(self._safe(
            "upsert_picks",
            lambda: self.repository.upsert_picks(picks),
            0,
        ) or 0)
        self.report.event_rows += int(self._safe(
            "upsert_observation_events",
            lambda: self.repository.upsert_observation_events(picks, self.run_id),
            0,
        ) or 0)
        self._write_report()

    def record_notification(self, pick: PickDecision, *, action: str, sent: bool) -> None:
        failures_before = len(self.report.failures)
        self._safe(
            "upsert_notification_state",
            lambda: self.repository.upsert_notification_state(
                pick,
                action=action,
                sent=sent,
                run_id=self.run_id,
            ),
        )
        if self.active and len(self.report.failures) == failures_before:
            self.report.notification_rows += 1
        self._write_report()

    def update_odds_metrics(self, metrics: dict[str, Any]) -> None:
        self.report.odds_metrics = dict(metrics or {})
        self._write_report()

    def finish(self, summary: dict[str, Any], *, status: str = "SUCCESS", error: str | None = None) -> None:
        if self._finished:
            return
        self._finished = True
        self.report.completed_at_utc = utc_now()
        self.report.summary = dict(summary)
        effective_status = status if not self.report.failures else ("SHADOW_PARTIAL" if status == "SUCCESS" else status)
        self._safe(
            "finish_workflow_run",
            lambda: self.repository.finish_workflow_run(
                self.run_id,
                run_type=self.run_type,
                status=effective_status,
                summary={**summary, "odds_discovery": self.report.odds_metrics, "shadow_failures": len(self.report.failures)},
                error=error,
            ),
        )
        self._write_report()

    def _write_report(self) -> None:
        path = self.output_dir / "shadow_database_report.json"
        payload = {
            "run_id": self.report.run_id,
            "run_type": self.report.run_type,
            "enabled": self.report.enabled,
            "shadow_mode": self.report.shadow_mode,
            "active": self.active,
            "started_at_utc": self.report.started_at_utc,
            "completed_at_utc": self.report.completed_at_utc,
            "fixture_rows": self.report.fixture_rows,
            "odds_rows": self.report.odds_rows,
            "pick_rows": self.report.pick_rows,
            "event_rows": self.report.event_rows,
            "notification_rows": self.report.notification_rows,
            "odds_metrics": self.report.odds_metrics,
            "failures": self.report.failures,
            "summary": self.report.summary,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
