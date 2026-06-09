"""refresh_nba_roster.py — nightly NBA roster refresh (05:00 UTC daily).

Re-fetches active player list from nba_api and rewrites
data/players_nba_active.json, then signals _courtvision_odds to reload its
in-process cache via reload_nba_roster().

Async scheduler interface (live_v2_app integration):
    from scripts.refresh_nba_roster import schedule_nightly
    create_supervised_task("roster_refresh", schedule_nightly)

Manual:
    python scripts/refresh_nba_roster.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_TARGET_HOUR_UTC = 5   # 05:00 UTC


def refresh_once() -> int:
    """Pull fresh roster, write JSON, bust in-process cache. Returns player count."""
    from scripts.build_nba_roster import build  # reuse build logic
    n = build()
    # Bust the in-process cache so the running API server sees the new file
    # without a restart.
    try:
        from api._courtvision_odds import reload_nba_roster
        n_cached = reload_nba_roster()
        log.info("roster_refresh: reloaded %d players into _courtvision_odds cache", n_cached)
    except Exception as exc:  # noqa: BLE001
        log.warning("roster_refresh: could not reload in-process cache: %s", exc)
    return n


async def schedule_nightly() -> None:
    """Sleep until 05:00 UTC, run once, repeat every 24 h.

    Wrapped by create_supervised_task → auto-restarts on crash.
    """
    while True:
        now_utc = datetime.now(timezone.utc)
        nxt = now_utc.replace(hour=_TARGET_HOUR_UTC, minute=0, second=0, microsecond=0)
        if nxt <= now_utc:
            from datetime import timedelta
            nxt += timedelta(days=1)
        wait_sec = (nxt - now_utc).total_seconds()
        log.info("roster_refresh: next run in %.0f s at %s", wait_sec, nxt.isoformat())
        await asyncio.sleep(wait_sec)
        try:
            n = refresh_once()
            log.info("roster_refresh: wrote %d players", n)
        except Exception as exc:  # noqa: BLE001
            log.error("roster_refresh: run failed: %s", exc)
        # Small buffer so we don't re-fire immediately due to clock jitter.
        await asyncio.sleep(60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    n = refresh_once()
    print(f"Done — {n} players written.")
    sys.exit(0)
