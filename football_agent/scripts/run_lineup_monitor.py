from __future__ import annotations

import os


def main() -> None:
    os.environ.setdefault("AGENT_RUN_TYPE", "lineup_monitor")
    # Frequent, lightweight run: only fixtures inside the dynamic T-65..T-45 minute
    # line-up window are analysed. Daily summary is disabled; only new/changed VALUE
    # alerts or withdrawals are posted.
    os.environ.setdefault("DAYS_AHEAD", "1")
    os.environ.setdefault("MAX_MATCHES", "120")
    os.environ.setdefault("ONLY_LINEUP_WINDOW", "true")
    os.environ.setdefault("ONLY_WATCHLIST_LINEUP_MONITOR", "true")
    os.environ.setdefault("LINEUP_WINDOW_START_MINUTES", "65")
    os.environ.setdefault("LINEUP_WINDOW_END_MINUTES", "45")
    os.environ.setdefault("SEND_DAILY_REPORT", "false")
    os.environ.setdefault("SEND_VALUE_ALERTS", "true")
    os.environ.setdefault("SEND_HEARTBEAT", "false")
    from football_agent.scripts.run_daily import main as run_daily_main

    run_daily_main()


if __name__ == "__main__":
    main()
