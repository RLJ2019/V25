from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional

import requests

from football_agent.database.models import DatabaseHealth


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "ja", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class DatabaseSettings:
    enabled: bool = False
    shadow_mode: bool = True
    fail_open: bool = True
    backend: str = "supabase_rest"
    supabase_url: str = ""
    secret_key: str = ""
    timeout_seconds: int = 20
    max_retries: int = 2
    batch_size: int = 250

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        # SUPABASE_SERVICE_ROLE_KEY remains accepted for users with the legacy key name,
        # but SUPABASE_SECRET_KEY is preferred. Neither value is ever printed.
        secret = os.getenv("SUPABASE_SECRET_KEY", "").strip() or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        return cls(
            enabled=_env_bool("DATABASE_ENABLED", False),
            shadow_mode=_env_bool("DATABASE_SHADOW_MODE", True),
            fail_open=_env_bool("DATABASE_FAIL_OPEN", True),
            backend=os.getenv("DATABASE_BACKEND", "supabase_rest").strip() or "supabase_rest",
            supabase_url=os.getenv("SUPABASE_URL", "").strip().rstrip("/"),
            secret_key=secret,
            timeout_seconds=max(3, _env_int("DATABASE_TIMEOUT_SECONDS", 20)),
            max_retries=max(0, _env_int("DATABASE_MAX_RETRIES", 2)),
            batch_size=max(1, _env_int("DATABASE_BATCH_SIZE", 250)),
        )

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.secret_key)

    @property
    def active(self) -> bool:
        return self.enabled and self.shadow_mode and self.configured

    def safe_summary(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "shadow_mode": self.shadow_mode,
            "fail_open": self.fail_open,
            "backend": self.backend,
            "configured": self.configured,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "batch_size": self.batch_size,
        }


class SupabaseRestClient:
    """Small, dependency-light Supabase PostgREST client.

    This client only runs server-side. The secret/service-role key must be stored in
    GitHub Actions Secrets and must never be written to artifacts or logs.
    """

    RETRYABLE_STATUS = {429, 500, 502, 503, 504}

    def __init__(self, settings: DatabaseSettings, session: Optional[requests.Session] = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.base_url = f"{settings.supabase_url}/rest/v1" if settings.supabase_url else ""

    def _headers(self, *, prefer: str | None = None) -> Dict[str, str]:
        headers = {
            "apikey": self.settings.secret_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        # New Supabase sb_secret_* keys are opaque API keys, not JWTs. Sending them
        # only as `apikey` lets the hosted gateway translate them to the service role.
        # Legacy service_role keys are JWTs and may also be sent as Bearer tokens.
        if not self.settings.secret_key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {self.settings.secret_key}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def request(
        self,
        method: str,
        table: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_body: Any = None,
        prefer: str | None = None,
    ) -> requests.Response:
        if not self.settings.configured:
            raise RuntimeError("Supabase database is not configured.")
        url = f"{self.base_url}/{table}"
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=dict(params or {}),
                    json=json_body,
                    headers=self._headers(prefer=prefer),
                    timeout=self.settings.timeout_seconds,
                )
                if response.status_code not in self.RETRYABLE_STATUS:
                    response.raise_for_status()
                    return response
                if attempt >= self.settings.max_retries:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else (1.0 * (2**attempt))
                except ValueError:
                    delay = 1.0 * (2**attempt)
                time.sleep(delay + random.uniform(0.05, 0.25))
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    raise
                time.sleep((1.0 * (2**attempt)) + random.uniform(0.05, 0.25))
        raise RuntimeError(f"Supabase request failed: {last_error}")

    def _batches(self, payload: list[dict[str, Any]]) -> Iterable[list[dict[str, Any]]]:
        size = self.settings.batch_size
        for start in range(0, len(payload), size):
            yield payload[start:start + size]

    def insert(self, table: str, rows: Iterable[Mapping[str, Any]]) -> None:
        payload = [dict(row) for row in rows]
        for batch in self._batches(payload):
            self.request("POST", table, json_body=batch, prefer="return=minimal")

    def upsert(self, table: str, rows: Iterable[Mapping[str, Any]], *, on_conflict: str) -> None:
        payload = [dict(row) for row in rows]
        for batch in self._batches(payload):
            self.request(
                "POST",
                table,
                params={"on_conflict": on_conflict},
                json_body=batch,
                prefer="resolution=merge-duplicates,return=minimal",
            )

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: Optional[Mapping[str, str]] = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        target = max(1, limit)
        page_size = min(1000, target)
        offset = 0
        collected: list[dict[str, Any]] = []
        while len(collected) < target:
            current_limit = min(page_size, target - len(collected))
            params: Dict[str, Any] = {
                "select": columns,
                "limit": current_limit,
                "offset": offset,
            }
            params.update(filters or {})
            response = self.request("GET", table, params=params)
            data = response.json()
            if not isinstance(data, list):
                raise RuntimeError(f"Unexpected Supabase response for {table}.")
            page = [dict(item) for item in data]
            collected.extend(page)
            if len(page) < current_limit:
                break
            offset += len(page)
        return collected

    def healthcheck(self) -> DatabaseHealth:
        if not self.settings.enabled:
            return DatabaseHealth(False, self.settings.configured, False, self.settings.backend, "Database disabled.")
        if not self.settings.configured:
            return DatabaseHealth(True, False, False, self.settings.backend, "SUPABASE_URL or secret key is missing.")
        try:
            self.select("workflow_runs", columns="run_id", limit=1)
            return DatabaseHealth(True, True, True, self.settings.backend, "Supabase REST connection OK.")
        except Exception as exc:
            return DatabaseHealth(True, True, False, self.settings.backend, f"Database healthcheck failed: {exc}")
