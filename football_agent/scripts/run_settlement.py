from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from football_agent.data.results import FixtureResultProvider
from football_agent.database.connection import DatabaseSettings, SupabaseRestClient
from football_agent.database.repository import DatabaseRepository
from football_agent.settlement.service import SettlementService, write_settlement_outputs


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "ja", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="V25.1.3 settlement pipeline")
    parser.add_argument("--mode", choices=["healthcheck", "dry_run", "settle"], default=os.getenv("SETTLEMENT_MODE", "dry_run"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("SETTLEMENT_LIMIT", "1000")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = DatabaseSettings.from_env()
    client = SupabaseRestClient(settings)

    if args.mode == "healthcheck":
        health = client.healthcheck()
        payload = {
            "mode": args.mode,
            "settings": settings.safe_summary(),
            "health": {
                "enabled": health.enabled,
                "configured": health.configured,
                "reachable": health.reachable,
                "backend": health.backend,
                "message": health.message,
            },
        }
        Path("output").mkdir(exist_ok=True)
        Path("output/settlement_healthcheck.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        if settings.enabled and settings.configured and not health.reachable and not settings.fail_open:
            raise SystemExit(1)
        return

    if not settings.enabled or not settings.configured:
        payload = {
            "status": "SKIPPED",
            "reason": "DATABASE_NOT_ENABLED_OR_CONFIGURED",
            "settings": settings.safe_summary(),
        }
        write_settlement_outputs(payload)
        print(json.dumps(payload, indent=2))
        if not settings.fail_open:
            raise SystemExit(1)
        return

    dry_run = args.mode != "settle" or env_bool("SETTLEMENT_DRY_RUN", args.mode != "settle")
    repository = DatabaseRepository(client)
    service = SettlementService(repository, FixtureResultProvider(), dry_run=dry_run)
    report = service.settle_once(limit=args.limit)
    report["mode"] = args.mode
    write_settlement_outputs(report)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
