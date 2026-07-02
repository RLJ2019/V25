from __future__ import annotations

import time
from typing import Any, Dict, Optional
import requests


class HttpClient:
    def __init__(self, timeout: int = 30, retries: int = 3, backoff: float = 2.0):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff

    def get_json(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = requests.get(url, headers=headers or {}, params=params or {}, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    return {"data": data}
                return data
            except Exception as exc:  # network/API failures are expected in CI without keys
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.backoff * attempt)
        raise RuntimeError(f"HTTP GET failed for {url}: {last_error}")
