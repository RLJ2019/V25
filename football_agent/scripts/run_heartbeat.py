from __future__ import annotations

import os


def main() -> None:
    os.environ.setdefault("AGENT_RUN_TYPE", "heartbeat")
    # Silent status update. It never sends loud alerts and is safe to schedule once
    # late in the afternoon/evening to reassure members when no value picks exist.
    os.environ.setdefault("DAYS_AHEAD", "2")
    os.environ.setdefault("MAX_MATCHES", "120")
    os.environ.setdefault("SEND_DAILY_REPORT", "false")
    os.environ.setdefault("SEND_VALUE_ALERTS", "false")
    os.environ.setdefault("SEND_HEARTBEAT", "true")
    os.environ.setdefault("HEARTBEAT_MIN_HOUR_UTC", "0")
    from football_agent.scripts.run_daily import main as run_daily_main

    run_daily_main()


if __name__ == "__main__":
    main()
