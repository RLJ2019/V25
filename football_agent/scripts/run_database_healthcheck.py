from __future__ import annotations

import json
from pathlib import Path

from football_agent.database.connection import DatabaseSettings, SupabaseRestClient


def main() -> None:
    settings = DatabaseSettings.from_env()
    health = SupabaseRestClient(settings).healthcheck()
    payload = {
        "settings": settings.safe_summary(),
        "health": {
            "enabled": health.enabled,
            "configured": health.configured,
            "reachable": health.reachable,
            "backend": health.backend,
            "message": health.message,
        },
    }
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "database_healthcheck.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if settings.enabled and settings.configured and not health.reachable and not settings.fail_open:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
